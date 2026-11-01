# SPDX-License-Identifier: GPL-3.0-or-later
"""Photos are always made anew: checked, upright, smaller, as JPEG – with the place, without anything else.

The requirement (NFA-084): every image is made anew so that it is efficient in storage and carries minimal metadata – but photos keep their location. Decided: every photo that a person sends to Rentalars – in the chat (UIX-049), as the photo of a defect, on
a receipt, at a material model or an item (MAT-090) – goes through :func:`render_photo_upload`:

* The file is checked by its content with Pillow (JPEG – an MPO of a phone is one –, PNG, GIF, WebP), by size in bytes and by
  the number of pixels in its header, before anything is decoded.
* The orientation the camera noted is applied, the long side becomes at most :data:`PHOTO_LONGEST_SIDE` pixels, transparency
  becomes white, and the photo is written as JPEG (the original is not kept).
* Of the metadata only two things stay: the colour profile (at most :data:`MAX_ICC_BYTES`; so that the colours of a phone's photo look right) and the **place**
  – the latitude, longitude and altitude of the GPS block (:func:`location_of`). The device, the time, the direction, the
  comment, the XMP block and everything else are gone. A place that is not plausible (a latitude of 200°, a text for a number)
  is dropped whole.
* The preview (:data:`THUMBNAIL_LONGEST_SIDE`) has no place and no device; only the colour profile (if it is at most
  :data:`MAX_ICC_BYTES`) is left in it.

Videos are the chat's own business (``chat.media``): ffmpeg makes them H.264/AAC of at most 720p and removes their metadata.
Documents that are kept as they came – the files of a project, the invoice of a purchase, the attachments of a mail, a logo – are not
touched here: a scan of a plan or an invoice must stay what it was.
"""

from __future__ import annotations

import io
import warnings
from dataclasses import dataclass
from typing import Any

from django.utils.translation import gettext as _

from rentalars.core.pictures import open_picture

#: The largest photo that is accepted (before it is made smaller).
MAX_PHOTO_BYTES = 25 * 1024 * 1024
#: PNG, GIF and WebP photos with more pixels are refused: they are decoded whole – 16 megapixels take 64 MB
#: as RGBA (UIX-049; a 6 KB PNG of 7070 × 7070 pixels took 593 MB with 50 megapixels allowed).
MAX_PHOTO_PIXELS = 16_000_000
#: A JPEG is decoded at a half, a quarter or an eighth of its size (``Image.draft``) and may be larger.
MAX_JPEG_PIXELS = 150_000_000
#: Formats decoded at a fraction of their size.
DRAFT_FORMATS = frozenset({"JPEG", "MPO"})

#: The long side of a stored photo, in pixels.
PHOTO_LONGEST_SIDE = 2048
#: The long side of a preview – of a photo, and the poster frame of a video.
THUMBNAIL_LONGEST_SIDE = 640
PHOTO_QUALITY = 85
THUMBNAIL_QUALITY = 80
#: The formats of photos accepted, as Pillow names them. MPO: a JPEG of a phone with a second picture.
PHOTO_FORMATS = frozenset({"JPEG", "MPO", "PNG", "GIF", "WEBP"})
#: The first bytes of BMP, TIFF and ICO: Pillow does not open them here (S1), so they are told apart by hand
#: to keep the helpful answer "photos are accepted as …".
OTHER_PICTURE_SIGNATURES = (b"BM", b"II*\x00", b"MM\x00*", b"\x00\x00\x01\x00")
#: Brands of the ISO file format that are pictures (HEIC of an iPhone, AVIF), not videos.
PICTURE_BRANDS = frozenset({b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1", b"avif", b"avis"})
#: A colour profile above this size is dropped (colours then read as sRGB): it is metadata, and the usual ones have
#: a few kilobytes.
MAX_ICC_BYTES = 128 * 1024


class PhotoError(ValueError):
    """A photo is refused; the text is the reason, in the language of the reader."""


@dataclass
class RenderedPhoto:
    """A photo as it is stored: the photo and its preview as JPEG, and the size of the photo."""

    photo: bytes
    thumbnail: bytes
    width: int
    height: int


def _megabytes(size: int) -> int:
    return size // (1024 * 1024)


def too_many_pixels(image_format: str | None, width: int, height: int) -> str:
    """Why a photo of this format and size is refused before it is decoded; empty if it is not (UIX-049)."""
    if image_format in DRAFT_FORMATS:
        if width * height > MAX_JPEG_PIXELS:
            return _("The photo has too many pixels: at most %(megapixels)d megapixels.") % {
                "megapixels": MAX_JPEG_PIXELS // 1_000_000
            }
        return ""
    if width * height > MAX_PHOTO_PIXELS:
        return _(
            "The photo has too many pixels: at most %(megapixels)d megapixels as PNG, GIF or WebP. Please send "
            "larger photos as JPEG."
        ) % {"megapixels": MAX_PHOTO_PIXELS // 1_000_000}
    return ""


def render_photo_upload(
    uploaded: Any,
    *,
    size: int | None = None,
    max_bytes: int = MAX_PHOTO_BYTES,
    not_a_photo: str = "",
    longest_side: int = PHOTO_LONGEST_SIDE,
    formats: frozenset[str] | None = None,
) -> RenderedPhoto:
    """Check an uploaded photo and make it anew (see the head of this module).

    Args:
        uploaded: The file (anything with ``read`` and ``seek``).
        size: Its size in bytes; by default taken from ``uploaded.size``.
        max_bytes: The most it may have before it is made smaller.
        not_a_photo: The text for a file that is no picture at all (the chat says "neither a photo nor a video").
        longest_side: The most pixels of the long side (a receipt: 2000).
        formats: The formats taken, if fewer than :data:`PHOTO_FORMATS` (a receipt: JPEG and PNG).

    Raises:
        PhotoError: Too large, too many pixels, not a picture, or a picture of a format that is not accepted.
    """
    from PIL import Image, UnidentifiedImageError

    not_a_photo = not_a_photo or _("This is not a photo.")
    formats = PHOTO_FORMATS if formats is None else formats & PHOTO_FORMATS
    if size is None:
        size = getattr(uploaded, "size", 0) or 0
    # UIX-049: the size in bytes before Pillow reads anything; then the header alone gives the
    # format and the number of pixels – nothing is decoded before both are checked.
    if size > max_bytes:
        raise PhotoError(_("The photo is too large (at most %(megabytes)d MB).") % {"megabytes": _megabytes(max_bytes)})
    try:
        with warnings.catch_warnings():
            # Pillow's own limit stays in force: above twice MAX_IMAGE_PIXELS ``open`` raises DecompressionBombError.
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with open_picture(uploaded, formats) as probe_image:
                image_format = probe_image.format
                problem = too_many_pixels(image_format, probe_image.width, probe_image.height)
                if image_format in formats and not problem:
                    probe_image.verify()
    except Image.DecompressionBombError as error:
        raise PhotoError(_("The photo has too many pixels.")) from error
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
        uploaded.seek(0)
        head = uploaded.read(12)
        if len(head) >= 12 and head[4:8] == b"ftyp" and head[8:12] in PICTURE_BRANDS:
            raise PhotoError(
                _("Photos in HEIC or AVIF cannot be read. Please send them as JPEG – phones do so when sharing.")
            ) from error
        if head.startswith(OTHER_PICTURE_SIGNATURES):  # a known picture format that is not taken here
            raise PhotoError(_("Photos are accepted as JPEG, PNG, GIF or WebP.")) from error
        raise PhotoError(not_a_photo) from error
    finally:
        uploaded.seek(0)
    if image_format not in formats:
        raise PhotoError(_("Photos are accepted as JPEG, PNG, GIF or WebP."))
    if problem:
        raise PhotoError(problem)
    try:
        photo, thumbnail, width, height = shrink_photo(uploaded, longest_side)
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as error:
        raise PhotoError(not_a_photo) from error
    finally:
        uploaded.seek(0)
    return RenderedPhoto(photo=photo, thumbnail=thumbnail, width=width, height=height)


# --- The place ----------------------------------------------------------------------------------------------


def _rational(value: Any) -> float:
    return float(value)


def location_of(image: Any) -> dict[int, Any]:
    """The place a photo was taken at, as the GPS tags that are kept; empty if there is none or it is not plausible.

    Kept: latitude and longitude with their hemisphere letters, and the altitude. Not kept: the time and date of the GPS
    block, the direction, the speed, the method – nothing that says more than "where".
    """
    from PIL import ExifTags

    try:
        gps = dict(image.getexif().get_ifd(ExifTags.IFD.GPSInfo))
    except Exception:
        return {}
    tags = ExifTags.GPS
    try:
        latitude = [_rational(part) for part in gps[tags.GPSLatitude]]
        longitude = [_rational(part) for part in gps[tags.GPSLongitude]]
        latitude_ref, longitude_ref = str(gps[tags.GPSLatitudeRef]), str(gps[tags.GPSLongitudeRef])
        if (
            len(latitude) != 3
            or len(longitude) != 3
            or latitude_ref not in {"N", "S"}
            or longitude_ref not in {"E", "W"}
        ):
            return {}
        degrees_north = latitude[0] + latitude[1] / 60 + latitude[2] / 3600
        degrees_east = longitude[0] + longitude[1] / 60 + longitude[2] / 3600
        if not (0 <= degrees_north <= 90 and 0 <= degrees_east <= 180):
            return {}
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return {}
    kept: dict[int, Any] = {
        tags.GPSLatitudeRef: latitude_ref,
        tags.GPSLatitude: tuple(latitude),
        tags.GPSLongitudeRef: longitude_ref,
        tags.GPSLongitude: tuple(longitude),
    }
    try:
        altitude = _rational(gps[tags.GPSAltitude])
        reference = gps.get(tags.GPSAltitudeRef, 0)
        reference = reference[0] if isinstance(reference, bytes) and reference else int(reference)  # a byte in EXIF
        if -1000 <= altitude <= 20000 and reference in {0, 1}:
            kept[tags.GPSAltitudeRef] = reference
            kept[tags.GPSAltitude] = altitude
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        pass  # the altitude is optional
    return kept


# --- Making the photo -----------------------------------------------------------------------------------------


def rgb(image: Any) -> Any:
    """The picture in RGB; what was transparent becomes white; a 16-bit grey scale is scaled down to 8 bits."""
    from PIL import Image

    if image.mode in {"I", "I;16", "I;16L", "I;16B", "I;16N"}:
        # Converted as it is, the values above 255 would all be white.
        image = image.point(lambda value: value * (1 / 256)).convert("L")

    if image.mode in {"RGBA", "LA", "PA"} or (image.mode == "P" and "transparency" in image.info):
        rgba = image if image.mode == "RGBA" else image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba)  # the alpha channel of an RGBA mask, without a copy of it
        return background
    return image.convert("RGB")


def jpeg(picture: Any, quality: int, icc_profile: bytes | None, location: dict[int, Any] | None = None) -> bytes:
    """A JPEG of the picture without the metadata of the original – only the colour profile and, if given, the place.

    No device, time, comment or XMP; EXIF holds the GPS block of ``location`` and nothing else.
    """
    from PIL import ExifTags, Image

    picture.info = {}
    stored = io.BytesIO()
    options: dict[str, Any] = {"format": "JPEG", "quality": quality, "optimize": True, "progressive": True}
    if icc_profile:
        options["icc_profile"] = icc_profile
    if location:
        exif = Image.Exif()
        exif.get_ifd(ExifTags.IFD.GPSInfo).update(location)
        options["exif"] = exif
    picture.save(stored, **options)
    return stored.getvalue()


def draft_size(width: int, height: int) -> tuple[int, int]:
    """The size to ask ``Image.draft`` for: the long side :data:`PHOTO_LONGEST_SIDE`, the short side in proportion.

        ``draft`` takes the largest of the scales 1/2, 1/4 and 1/8 that keeps both
        sides at least this large – so the decoded long side never falls below
    :data:`PHOTO_LONGEST_SIDE` (UIX-049).
    """
    if max(width, height) <= PHOTO_LONGEST_SIDE:
        return width, height
    if width >= height:
        return PHOTO_LONGEST_SIDE, max(1, height * PHOTO_LONGEST_SIDE // width)
    return max(1, width * PHOTO_LONGEST_SIDE // height), PHOTO_LONGEST_SIDE


def shrink_photo(handle: Any, longest_side: int = PHOTO_LONGEST_SIDE) -> tuple[bytes, bytes, int, int]:
    """Make a photo smaller: upright, at most ``longest_side`` pixels, with the place and without other metadata.

    Returns:
        The photo and its preview as JPEG, and the width and height of the photo.
    """
    from PIL import Image, ImageOps

    longest = (longest_side, longest_side)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", Image.DecompressionBombWarning)
        with open_picture(handle, PHOTO_FORMATS) as image:
            # UIX-049: checked again here, before anything is decoded.
            if too_many_pixels(image.format, image.width, image.height):
                raise Image.DecompressionBombError(f"{image.width} × {image.height} pixels")
            location = location_of(image)
            if image.format in DRAFT_FORMATS:
                # A large JPEG is decoded at a half, a quarter or an eighth of its size where its long side
                # still has PHOTO_LONGEST_SIDE pixels: far less memory for the photo of a 100-megapixel
                # camera – and for a panorama, whose short side is shorter than that.
                image.draft("RGB", draft_size(image.width, image.height))
            icc_profile = image.info.get("icc_profile")
            if icc_profile and len(icc_profile) > MAX_ICC_BYTES:
                icc_profile = None
            image.load()
            ImageOps.exif_transpose(image, in_place=True)
            picture = rgb(image)
    picture.thumbnail(longest, Image.Resampling.LANCZOS)
    preview = picture.copy()
    preview.thumbnail((THUMBNAIL_LONGEST_SIDE, THUMBNAIL_LONGEST_SIDE), Image.Resampling.LANCZOS)
    return (
        jpeg(picture, PHOTO_QUALITY, icc_profile, location),
        jpeg(preview, THUMBNAIL_QUALITY, icc_profile),
        picture.width,
        picture.height,
    )

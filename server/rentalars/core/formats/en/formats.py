# SPDX-License-Identifier: GPL-3.0-or-later
"""English formats of Rentalars: British – day before month, 24-hour clock, decimal point (UIX-029).

Django's plain ``en`` writes American dates ("10/25/2006", "2:30 p.m."). Rentalars' English is British, and
times are always written with 24 hours, as in German.
"""

DATE_FORMAT = "j F Y"  # 25 October 2006
TIME_FORMAT = "H:i"  # 14:30
DATETIME_FORMAT = "j F Y H:i"  # 25 October 2006 14:30
YEAR_MONTH_FORMAT = "F Y"  # October 2006
MONTH_DAY_FORMAT = "j F"  # 25 October
SHORT_DATE_FORMAT = "d/m/Y"  # 25/10/2006
SHORT_DATETIME_FORMAT = "d/m/Y H:i"  # 25/10/2006 14:30
FIRST_DAY_OF_WEEK = 1  # Monday

DATE_INPUT_FORMATS = [
    "%d/%m/%Y",  # 25/10/2006
    "%d/%m/%y",  # 25/10/06
    "%Y-%m-%d",  # 2006-10-25
]
TIME_INPUT_FORMATS = [
    "%H:%M:%S",
    "%H:%M:%S.%f",
    "%H:%M",
]
DATETIME_INPUT_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%y %H:%M",
]
DECIMAL_SEPARATOR = "."
THOUSAND_SEPARATOR = ","
NUMBER_GROUPING = 3

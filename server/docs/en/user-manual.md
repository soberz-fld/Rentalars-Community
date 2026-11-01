# User manual

Rentalars, version 1.0.0

This manual explains how to work with Rentalars: maintaining, inspecting –
electrical devices after DGUV V3 with measured values –, auditing and
labelling material and products, entering purchases with their invoice,
subscribing to the bookings of material in your own calendar,
planning and costing projects – large
productions also as a whole project with subprojects –, putting the vehicles
and trailers of the fleet on a project's trips, handling service
cases quickly, checking availability, packing, issuing and taking back,
writing offers, order confirmations, delivery notes and invoices and passing
them to accounting, keeping an eye on profitability, scheduling personnel
with surcharges, recording times
and expenses, corresponding with customers about the project and with the
team in the project's chat, seeing addresses on the map and a project's
trips with their route, keeping track of the coming weeks, letting
Rentalars answer by itself with automations and keeping other programs up
to date via webhooks – and, collecting incoming invoices,
keeping the book values of equipment, scanning labels, logging in with
the company directory and letting freelancers name their price. Packing lists and times are also available on the road
without a network, with the companion app for Android (section 2). For
installing and running the server there are separate guides, which you can
also open here in the manual: [Installation](operations/installation.md),
[Operation](operations/operation.md), [Updating](operations/updating.md),
[Backup](operations/backup.md), [Encryption](operations/encryption.md) and
[Taking over the material list](operations/import.md).

Rentalars speaks English and German – each person chooses their own
language (section 2, "My account"). This manual exists in both languages,
also inside Rentalars: "Manual" at the bottom of the sidebar opens it in
your language.

**Contents**

1. [The essentials in five minutes](#1-the-essentials-in-five-minutes)
2. [Logging in and finding your way around](#2-logging-in-and-finding-your-way-around)
3. [First steps after installation](#3-first-steps-after-installation)
4. [Material](#4-material)
5. [Products](#5-products)
6. [Customers](#6-customers)
7. [Planning projects](#7-planning-projects)
8. [Prices](#8-prices)
9. [Availability, shortages, subrental](#9-availability-shortages-subrental)
10. [Packing, issue, return](#10-packing-issue-return)
11. [Documents](#11-documents)
12. [Personnel](#12-personnel)
13. [Time tracking](#13-time-tracking)
14. [Correspondence](#14-correspondence)
15. [Planning and overview](#15-planning-and-overview)
16. [Settings](#16-settings)
17. [What this version cannot do yet](#17-what-this-version-cannot-do-yet)
18. [Questions and answers](#18-questions-and-answers)

---

## 1. The essentials in five minutes

Rentalars distinguishes three things that often go by the same word in
everyday work:

| Term | What it is | Example |
|---|---|---|
| **Material model** | an article type as it appears in the manufacturer's catalogue | "Cordial CPM 5 FM" |
| **Item** | a single piece of it, with its own ID on the sticker | `0001`, `0002`, … |
| **Product** | what you plan, offer and charge for | `K-005` "XLR cable 5 m", €1.50 per day |

The customer does not hire a "Cordial CPM 5 FM" but an "XLR cable 5 m" – and
they do not care which manufacturer it comes from. That is why a
**product** often has several **models** attached: twelve cables from
Cordial and eight from Sommer Cable together make twenty pieces of `K-005`.

**A product has no stock that anyone maintains.** Its stock is the number
of items assigned to it. If a cable breaks, you set the item to
"defective" – and the product has one fewer.

Material that **belongs to a customer** and is stored with you – a band's
mixing desk and multicores that you take along to their gigs – is handled
in exactly the same way: as a product with a model and items, but with the
customer as **owner** and without a price (section 5, "Customer
material").

A **project** is an event, rental or production for a customer, with a
number such as `2026-0042`. It contains **lines** ("12 × K-005"), which
can be organised into **groups** ("Sound FOH", "Lighting stage") – also
nested ("Lighting › Front truss"). Personnel, vehicles
and trailers are not in the groups but in blocks of their own below them
(section 7, "Logistics"). A large production, say a city festival
with several stages, you plan as a **whole project** with **subprojects**,
each with its own period, material, personnel and status (section 7,
"Subprojects"). An existing project can also be divided up like this
later. For a fault, a question or a repair that needs no planning there is
the **service case** – with a number and correspondence like a project, but
without material and personnel (section 7, "Service cases").

A few words mean the same everywhere in Rentalars (the list for contributors is `docs/dev/glossary.md`):

| Word | Meaning | Not meant |
|---|---|---|
| **Container** | a case, rack or road case that holds other material | "device" |
| **Device** | only an electrical device or a fixture (electrical inspection, MVR file) | a case or rack |
| **Crew** | the people planned on one project | the area "Personnel" |
| **Personnel** | the area of administration: people, job functions, times, costs | the crew of a project |
| **Out** | material that was issued and not taken back yet (German "unterwegs") | the rental period ("Material out of house") |
| **Inquiry** | a project with the status "Inquiry", or a mail that can become a project | the **crew request** to a person |
| **Order** | what a customer gives ("order confirmation") | a **job** that runs in the background |

The common thread:

```
Material ──▶ Products ──▶ Plan project ──▶ Availability ──▶ Packing ──▶ Issue ──▶ Return ──▶ Invoice
 (what we      (what we       (what, when,       (is there
  have)         offer)         for whom,          enough?)
                               how much)
```

Along the way the **documents** for the customer are created – offer,
order confirmation, delivery note, invoice – and for the crew the crew
disposition (section 11). Every document a customer got is
listed under Accounting → Outgoing documents (section 11, "Outgoing
documents"). If you wish, invoices are passed on to Lexware Office or as a
DATEV file to your tax adviser (section 16, "Accounting").

---

## 2. Logging in and finding your way around

### Logging in

Open the address of your Rentalars in the browser and log in with your
user name (or e-mail address) and password. An up-to-date browser is all
you need – on a computer, a tablet or a phone.

- **Forgot your password?** "Forgot your password?" on the login page sends
  you a link to your e-mail address – even if you have been invited but
  have never set a password.
- **Mistyped too often?** After five failed attempts the name is locked for
  15 minutes. After that it works again by itself.
- **New to the team?** Every person in Personnel has their own login
  (section 12). You receive an e-mail with a link through which you set
  your password yourself – or, for example if you have no e-mail address, a
  **one-time password**, in person or by phone. You use it to log in once;
  after that Rentalars first asks for a password of your own ("Choose your
  password"). Nothing else can be done before that.
- **Two-factor login:** If you have set it up (below, "My account"),
  Rentalars asks for the six-digit code from your authenticator app after
  the password. Phone not to hand? One of your recovery codes works too –
  each exactly once.
- **Company directory (LDAP, Active Directory)**. If your
  company keeps its accounts in a directory and the administrator has
  switched this on (section 16, "Directory (LDAP)"), you log in with the
  name and password you use for the rest of the company network – you
  do not set a password in Rentalars, and "Forgot your password?" does not
  apply to you; the password is changed where it lives, in the directory.
  Your roles come from the groups you are in there and are brought up to
  date at every login. At your first login Rentalars creates the account. If you
  have an account in Rentalars already, it is linked to the directory only if
  your administrator has linked it (or switched on linking by name); otherwise
  the login through the directory is refused and you keep using your own
  password. If you are in none of
  the groups that have a role, you cannot log in. Two-factor login works as
  above: first the directory password, then the code. If the directory does
  not answer, the login says so ("The company directory could not be reached
  just now") in addition to "Name or password are wrong."; then try again
  later or ask your administrator. Accounts that the administrator marked as
  **local (emergency) accounts**, and accounts that have all rights, always
  log in with the password of Rentalars.
- **Logged out without meaning to be?** After a period without activity –
  four hours by default – Rentalars logs you out. Simply log in again; you
  end up on the page you wanted to open.

### The sidebar

At the top of the sidebar are the Rentalars **logo** – a click takes you to
the start page; the same logo is the icon in the browser tab and on the
phone's home screen if you put Rentalars there – and the **search field**
(below, "Start page and search"). Under the logo and "Rentalars" the **name
of your company** from Settings → Company data and settings appears
in small print. That way you always see which installation you are in –
handy if you have a second one for trying things out. If someone changes
the name, the next page shows the new one. Below that are the areas:

| Entry | Content |
|---|---|
| **Projects** | all projects and subprojects, their planning with the subrentals and the logistics, prices, documents and files, the schedule with the journeys, packing lists, correspondence, chat and the overview for the crew; the open items; the service cases; the project templates; the inquiries – mails that do not yet belong to a project, and inquiries noted by hand (section 14) |
| **Planning** | calendar, timeline, material utilisation, personnel plan and shortages (section 15) |
| **Material management** | products and kits (the first tab), models, items, the fleet (right after the items), "Open points" (with the number of open points), inspections, "Audit", the import; "Enter a purchase" and, in the head of every tab, the field "Item ID" (section 4) |
| **Accounting** | the **outgoing documents** – every document a customer got, with their sums (section 11, "Outgoing documents") – and the **monthly statement** of the service cases (section 7, "Monthly statement"); also the **incoming invoices**, the **asset register**, the **sales from stock** and **import of old projects** (section 11 and section 4); each tab only for whoever may use it |
| **Customers** | customers with their addresses and contacts, venues – with route and map (section 6) |
| **Personnel** | people with their login, their job functions, hourly and day rates and qualifications, their availability; approving and reporting on times and expenses (section 13) |
| **Reports** | the profitability of the projects and what the material has earned – for everyone with the module Reports who may read every project and see prices (section 8, "Reports") |
| **My area** | what you do for yourself: your deployments (the first tab), your availability, your times, your expenses, your personnel data (section 12) |
| **Settings** | in boxes by topic: Company (with the labels), Users and rights, Processes (automations, notifications, AI), Projects and personnel (surcharges, rental scales, job functions), E-mail, Documents and accounting, Master data, Import and export, Interface for other programs, Operation and security (section 16) |

At the bottom of the sidebar – on the phone at the top next to the menu –
is the **bell** with the number of your unread notifications (section 15).
It keeps count on every page, even without reloading.

Below it, on every page, is the **"Record time"** button – on the phone the
clock at the top right (section 13).

Under your name, one below the other, are **"My account"** (below),
**"Manual"** and **"Log out"** – each in a row of its own with
an icon, easy to hit on the phone too. "Manual" opens this manual in your
language. **The manual comes in chapters:** "Manual" shows the
table of contents – the introduction, a **search** over all chapters (the
hits name the chapter and the section and jump straight to it) and the
18 chapters, each with a short description and its sections –, and a click
on a chapter opens **only that chapter** (`/manual/3/` is chapter 3), with
"Previous chapter", "Contents" and "Next chapter" above the text, the two
neighbouring chapters by name below it, and the list of chapters – with the
sections of the open one – beside it. Links with an anchor (`/manual/#7-planning-projects`)
jump to the right chapter. The operations
guides are part of it as well, listed below the table of contents, and links to them open them directly. If a language has no manual yet, Rentalars shows the
German one with a note.

At the very bottom are the **version number** ("Rentalars 1.0.0") and below
it **"by fld-vt.de"** – the note saying who developed Rentalars; the link
opens their website in a new tab. You will find the same note below the
login window. An additional term of the licence (GPL, section
7 b; file `ADDITIONAL-TERMS.md`) requires whoever conveys Rentalars to
keep this note with its link; adding to it is allowed, removing it is not.
Whoever only runs it without conveying it is not affected. "About Rentalars"
(a link next to the note) shows the licence, the copyright and the libraries
Rentalars uses.

Under an entry there are often **tabs**, for example under Personnel
"People", "Availability", "Job functions", "Approve", "Report" and
"Expenses", under Projects "Projects", "Open items", "Service cases" and
"Inquiries", under Accounting "Outgoing documents" and
"Monthly statement".
Every tab is a start page of the area; what explains it is
directly below the tabs. The header with the heading is the same height on
all pages, so the tabs are always in the same place.

You only see what your role gives you access to. If an entry or a button
described in this manual is missing, you lack the right for it – talk to an
administrator. The same applies to **prices**: they are a right of their
own. Anyone who does not have it sees the planning without price columns.

**Using it on the phone.** On the phone – and in windows up to 900 pixels
wide, where the bar with the menu button appears at the top – the sidebar
is hidden behind the menu button at the top right. The menu
slides in from the right over the dimmed page, as in the app. You open it
with the menu button or by swiping from right to left anywhere on the
page; the menu follows your finger. If you swipe on something that scrolls
sideways by itself, such as a timeline or a wide table, that scrolls and
the menu stays closed. You close it with the cross, by tapping beside the
menu, by swiping it to the right, with Esc or with the Back button – you
stay on the page. The menu holds everything the sidebar holds on the
computer: name and company, the areas (the current one marked orange),
"Record time", notifications, your account, "Log out" and the version.
The **magnifying glass** next to the menu button opens it with the cursor
already in the search field. On the phone, the name of your company also
appears in the header bar under "Rentalars" (if it is too long, it ends
with "…"). On the computer the sidebar stays as it is.

Rentalars appears **dark**, in your house colours: orange for everything
you are meant to click or that stands out, light grey for text. Whatever is
printed – packing list, price overview, timesheet, labels, documents – stays
black on white.

The pages follow the rules for accessible websites (WCAG 2.1, level AA) –
also for use with the keyboard and with a screen reader. A
screen reader also reads out the help text of a field, such as "Empty: as
the model – …". If you work with
the keyboard: the first press of the Tab key shows **"Skip to content"** –
this skips the sidebar.

### Start page and search

The start page shows what concerns you **now** – each time only what you
have the rights for:

- **New for you:** unread notifications.
- **You are asked:** deployments you are to accept or decline – with the
  buttons right next to them.
- **Your follow-ups:** projects whose follow-up is due for you, with their
  note, "overdue" if the day has passed, and "Done", with the time if it
  has one; "All my follow-ups" leads to Planning → Follow-ups
  (section 15). A service case carries the label "Service case" there.
- **Invoices still to be written:** closed projects that have
  no invoice yet – your own first; "All" leads to the project list,
  filtered to closed projects without an invoice (section 11, "Invoices
  still to be written"). Only with the right to see prices.
- **My service cases:** the service cases you are responsible for or
  involved in and that are not yet done, with status; "All my service
  cases" leads to My area → "Service cases" (section 7, "Service cases").
  A case in the **backlog** is missing here and among the follow-ups until
  its follow-up is due.
- **My deployments:** project, job function, time and meeting point; a
  running deployment with "Running since …". "All my deployments" leads to
  My area → "My deployments" (section 12, "My area").
- **Coming up** and **Out at the moment:** the next projects and what has
  been issued – also partly ("partly issued").
- **To pack today and tomorrow**, **Expected back today** – for the
  warehouse; anything overdue is marked.
- **Open items:** projects where something still needs to be clarified.
- **Open shortages:** all open shortfalls, not just those of the next few
  weeks. The first six are shown; the button next to them ("12 in total")
  leads to the whole list (section 9).
- **E-mail:** which mailbox cannot be fetched and how many inquiries and
  mails with an unknown reference are waiting for a project.

The boxes sit in an even grid; whatever does not concern you is left out
entirely.

**Search** is available on every page: at the top of the sidebar, on the
phone behind the magnifying glass, and on the keyboard with the **"/"** key
– it puts the cursor in the search field as long as you are not typing in
a field. The start page also has a large search field. The search finds
projects, service cases, customers, venues, products, material, people and
mails – by name, project number (also a project's former one, such as
`P-2026-0042` for `2026-0042`; section 7, "Creating a project"), article
number, material ID, serial number, the value of a custom
field (except confidential ones; section 4, "Custom fields") or subject.
If you type in the ID `0742`
from the sticker, you land on the item – it is even quicker with the QR
code on the label: the phone's camera opens the item's page directly
(section 4, "Labels"). Mails are only found by those who are allowed to
read them – those with a lock only by those who also see
prices (section 14). A subproject is listed with "part of 2026-0042
Stadtfest", and the name of a whole project also finds its subprojects.

**Readable addresses.** A project can be reached under its project number,
a product under its article number: `…/projects/2026-0002/`,
`…/products/L-010/`. Links like these can be passed on and saved as
bookmarks. Older bookmarks with the internal number still lead to the
target, as do links with the former project number
(`…/projects/P-2026-0002/`): they redirect to today's address.

### Lists

All lists work the same way:

- **Filter** using the fields behind the **"Filters"** button above the
  list (below, "Expanding and collapsing filters").
- **Sort** by clicking a column heading; a second click reverses the order.
  A small triangle (▲ or ▼) shows what is currently being sorted by.
  Filters and page length are kept. Every column heading sorts,
  including columns you add under "Columns" and calculated columns such as
  the totals of a project, the stock or the category-specific value.
  Rentalars sorts calculated columns for lists of up to 2,000 rows; if the
  list is longer, it appears in its usual order, and a note asks you to
  narrow it down with the filters. Rentalars sorts numbers in text as you
  would read them: "5 m" before "10 m". For columns with several values
  (such as a person's job functions) the first one in the alphabet counts.
  Only columns with buttons or tick boxes do not sort.
- **Entries per page:** at the bottom right of every list – 25, 50, 100 or
  200, next to them the field **"Own number"** for a whole
  number from 5 to 1,000; "Show" applies it, also without JavaScript.
  Rentalars refuses any other number with a note at the field, and the list
  stays as it was. The default is 50. Rentalars remembers the
  choice **for you and for this list** – in your account, so also after
  your next login and on another device; every list keeps its own number.
  A
  link with another number takes precedence and is then remembered for
  this list. This holds for every table that loads page by page, also for
  the lists of the master data; tables that are a form or a sum as a whole
  are the exception – Approve, My times, the totals of the reports and the
  rules of the automations.
- Filters, sorting and page length are part of the page's address. You can
  save a filtered view as a bookmark or send it as a link.

**Every list is a table.** Everything this section
describes – filters, columns, sorting, CSV and grouping – applies to every
list in Rentalars: also to service cases, inquiries, expenses and My
expenses, open items, project templates, inspections, shortages,
automations and their runs, notifications, follow-ups, roles, security log,
webhooks and tasks in the background. Not tables of this kind are small
tables on an entry's page (such as a project's lines or its files), the
change log (it has its own filters), "My times", "Approve" and the report
on times, the rental scales and Personnel → Availability.

**Choosing rows and bulk actions**. Each row of the tables
starts with a **tick box**; the box in the header row chooses all rows of the
page. As soon as you have chosen something, the **bar of the choice** appears
at the lower edge with the number of the chosen rows. Everywhere:

- **"Download chosen as CSV"** downloads only the chosen rows – with the
  columns you have set – as CSV;
- **"Clear choice"** takes all ticks away.

Some lists add actions to the bar:

- **Projects:** **"Set follow-up"** (date and time, for whom, a note) and
  **"Take off follow-up"** for all chosen projects.
- **Service cases:** **"Set status"** (with the reason for "waiting"),
  **"Set follow-up"** and **"Take off follow-up"** as well as
  **"Set person responsible"**.
- **Outgoing documents** (Accounting): **"Download chosen documents (ZIP)"** –
  for each document the PDF and, if there is one, the XRechnung, named after
  the document number; up to 300 documents in one download.

Each row is checked on its own: whatever you may not change for a project or
service case (right, closed project, a project instead of a service case) is
skipped, and the message names the skipped rows with the reason; the others
are changed. Up to 1,000 rows can be chosen together. Tables whose rows are
computed and have no entry of their own have no tick boxes. The tables that
already have a bar of their own – items, inspections and open to-dos, if you
may change the material – keep it and have **no** "Download chosen as CSV"
(whoever may only read has it). In the overview of inspections the box
chooses an item with all its kinds of inspection. The choice applies to the
page you see; if you page on, it starts anew. With more than about 150 chosen
rows Rentalars keeps the choice in your session (the address of the CSV file
stays short) – that address holds only there. API: `POST
/api/v1/projects/bulk` (write access to the module "Projects") and `POST
/api/v1/service-cases/bulk` (the same, or whoever works on service cases – as
in the browser, Rentalars decides per case).

**Expanding and collapsing filters.** Above the lists – projects, items,
models, products, inspections, customers, venues, people, approving and
reporting on times, shortages, mail, change, access and security log, a
webhook's deliveries and, all other tables – the filters sit
behind the **"Filters"** button; the **search field** in front of it always
stays visible. The filters are collapsed every time you open a list – on
every screen, even if you had expanded them before; a click or tap on
"Filters" expands or collapses them. If filters are set, the button shows
their number, such as **"Filters (2 active)"**, and while they are
collapsed, what is filtered is shown next to it, such as "Status:
Confirmed" – so you always see why the list is shorter. This also applies
in material management and in the master data lists; there the heading of
a set filter names the selection, such as "By Active: Yes". If a filter has
an error, it is never collapsed, so that you see it. With collapsed
filters, you search by typing the term and pressing Enter (on the phone
"Search" or "Go"). Without JavaScript there is no button, and all filters
are shown open.

**Choosing columns.** Every table – from projects, products and items to
service cases and expenses – has the **"Columns"** button above the table.
It expands the list of all columns available: ticking a box shows a
column, unticking it hides it, "Apply" saves the choice. For items, for
example, you can add product, storage location, manufacturer, short name
and the reason for the status; for projects, totals such as man-hours,
revenue, costs and profit (section 8, "Totals in the project list"). The
column that identifies a row (such as an item's ID) always stays. Rentalars
remembers the choice for you and for this list – in your account, so also
on another computer. **"Default columns"** restores the original
selection. Columns for which you lack a right (such as prices) are not
offered at all.

**Downloading as CSV.** Next to it are two links:

- **"CSV"** delivers the list as you see it – with the columns shown,
  filtered and sorted, but with all rows, not just the current page.
- **"CSV with all columns"** delivers the same rows with every column you
  are allowed to see.

The file has a semicolon as separator and writes numbers and dates in the
language of the interface – in English with a decimal point and dates as
`31/12/2026`, in German with a decimal comma and dates as `31.12.2026`;
column names, "yes"/"no" and the file name follow it too. Excel and
LibreOffice open it, umlauts included. A file exported
from the list of products, customers or people can be imported again after
editing (section 16, "Import and export"). Columns with buttons or tick
boxes are never in the file.

**Group by.** Next to "Columns" is **"Group by"**: if you choose a column –
for service cases the status, for example, for inquiries the sender or the
mailbox, for projects the customer –, the rows appear under one heading per
value, and next to each heading it says how many entries the group has in
the whole filtered list. Values with a fixed order appear in that order
("open, in progress, done"), customers and the like by name; rows without
a value appear under "(no entry)". Within a group, the sorting you chose
applies. If a group continues on the next page, its heading appears there
again. Filters and sorting are kept when grouping, and like them the
grouping is part of the page's address. The **CSV file** is never grouped.

You can choose **every column that is shown** under "Group
by", in the order of the table; only columns with buttons or tick boxes
are missing. If you hide a column, it also disappears from the choice.
Columns with a date and time group by the day, a period by its first day.
Computed columns (totals, stock, number of projects …) group lists of at
most 2,000 rows; if the list is longer, Rentalars says so above the table
and shows it without groups – narrow it down with the filters. "Approve"
stays grouped by project, and the totals of the report are groups already;
neither has "Group by". The lists of the master data can also be grouped
by every column shown, for example storage locations by their path.

### Back

On every page below the lists – a product, an item, a form – **"← Back"**
is at the top left. It leads to the view you came from, exactly as you
left it: to the list with its filter and on the same page, to the search
result, or to the item from which you opened the product.

Unlike the browser's back button, after editing and saving it does not
lead into the form again. The tabs of a project, a person, a product, a
model and an item count as one page: "Back" leaves the record. If you open
a page via a bookmark or a link, "Back" takes you to the area's list. "Back" also leads to the page opened last when you have used the
browser's back button before: it used to jump to the last product you had
seen afterwards. (This works as long as the browser sends the page it came
from, which it does by default; otherwise it behaves as before.)

The tabs under a sidebar entry – such as Calendar, Timeline, Material
utilisation, Personnel plan and Shortages under "Planning" or Customers
and Venues under "Customers" – are start pages and show no "Back"; the
pages below them always do. This applies to every page you open via the
sidebar, the links at its foot or a tab – also for
service cases, expenses and My expenses, and for every new tab such as
Planning → Follow-ups or My area → Service cases. **On the phone** "Back"
is always at the top left of the header bar; on the start pages it leads to
wherever you were in Rentalars before.

### Confirmations and pages that update themselves

**Confirmations** – "Delete this line?", "Anonymise this person?" – appear
as a Rentalars dialog, not as a grey browser window. "Cancel" leaves
everything as it is; the other button carries out the action. It is named
like the action ("Delete person", "Anonymise") or simply "Yes, delete" –
red if something is deleted or removed.

**Pages stay up to date.** A project's pages – all tabs – and the
inquiries (Projects → Inquiries) follow changes by themselves: if a mail
arrives for the project or someone else changes something in it – a line,
the status, a packing list –, the page reloads after about 20 seconds at most
and stays at the same position. If you are typing something or a dialog is
open, nothing is lost: then only the note **"There is something new on
this page."** appears at the bottom with the **"Show"** button, and you
reload when it suits you. What you save yourself does not trigger a reload
– what someone else changed shortly before or after is still shown by the
page, such as the acceptance of a deployment request (section 12). An open **packing list** also follows ticking off: if someone else ticks
something off – in the browser or with the companion app –, it reloads
after 20 seconds at most (while you are typing the note appears instead).
An open **planning** also follows the **stock** (section 7, "The
planning follows the stock"). The number on the bell is up to date on every page. A new message in a
project's **chat** does not reload any page: the number of unread messages
appears on the "Chat" tab, and the chat itself shows new messages by
itself (section 7, "Chat in the project") – including every change to a
message, even two changes in the same second.

### Required fields

You recognise required fields by the red **asterisk \***; at the top of the
form "\* Required field" appears once. Some fields are only required under
a condition – the price for rental products, the sale price for sale
products, the customer for a project that is not internal, or the IMAP
details for a correspondence mailbox. Their asterisk appears as soon as the
condition is met, for example when you choose the product kind.

This holds without exception: on every page and in every
dialog, in the forms of the master data and in forms with many rows such as
"Enter a purchase". A group of option buttons carries the asterisk at its
heading. A screen reader learns from the field itself that it is required.

### Choosing date and time

Every field for a date, a time or both has a **calendar or clock icon** on
the right. It opens a calendar as with "Choose the period in the calendar"
(below), and for a time on its own the clock face straight away:

- **A date** you take over with a tap on the day.
- **Date and time:** after the day you choose the time on the **clock
  face** – first the hour (outer ring 1 to 12, inner ring 13 to 23 and 00),
  then the minute. The clock face shows steps of five minutes; by dragging
  or typing into the "Hour" and "Minute" fields you get any minute.
  **"Apply"** enters the value in the field.
- **"Today"** or **"Now"** sets the current day or the current time,
  **"Clear"** – only for fields that are not required – empties the field.
- **With the keyboard:** in the field Alt+↓, in the calendar the arrow keys
  (Page Up and Page Down leaf through the months), Enter chooses the day; on
  the clock face the arrow keys change the value, Enter goes from the hour
  to the minute and then applies. Esc closes without changes.
- **On the phone** a tap in the field already opens the picker; day and
  time come one after the other there.

Typing directly into the field still works. Only this
one icon appears in the field; the browser's own calendar or clock icon
that some browsers showed next to it is hidden or covered. If the field
belongs to a period, the other day of the period is outlined in the
calendar and the days in between are shaded.

### Entering periods

Wherever a form asks for a period with a start and an end – the project, a
line, a crew line, an absence, a blocked period –, the two fields help each
other:

- **"until" cannot be before "from".** If the end is before the start,
  Rentalars sets it to the start.
- **The end moves along.** If you move the start, the end moves along and
  the period keeps its length – forwards as well as backwards: "Fri 12:00
  until Sat 12:00" becomes "Sat 12:00 until Sun 12:00" after moving the
  start to Saturday 12:00. The length is counted by the clock, so 12:00 to
  12:00 stays 12:00 to 12:00 even across the change to or from summer
  time. Then you set the end as you need it.
- **"Choose the period in the calendar"** next to the fields opens a
  calendar: the first click chooses the first day, the second the last. For
  fields with a time, "From (time)" and "Until (time)" appear below; they
  have the clock face too (above). "Apply" enters everything in the fields.
  If the end is on the same day and not after the start – 12:00 to 12:00
  –, the following day is meant.
- **The project's other periods** are **hatched** in these calendars so
  that you quickly find your way around: the rental period grey, the event
  green, with lines in opposite directions; the legend below the calendar
  names the times. In the project form the event is hatched in the
  calendar of the rental period as soon as you have entered it, and vice
  versa; when creating or changing a phase both are hatched (section 7).

### My account

At the bottom of the sidebar, under your name: change your password – if
your account is kept in the company directory, you change it there, and
the page says so (above, "Logging in") – and
manage API tokens (section 16). Because every account is also a person in
Personnel, **"My personnel data"** leads from there to your contact
details, deployments and absences; your availability and your calendars
are in the menu under **"My area"** (section 12). Also:

- **Two-factor login.** After the password Rentalars then asks for a code
  from an app on your phone – FreeOTP, Aegis, a password manager or the
  authenticator from Google or Microsoft. Setting it up: scan the QR code
  with the app, enter the code it shows, done. Rentalars then shows **ten
  recovery codes** – write them down or print them and keep them separately
  from your phone; each one replaces the app once. They are shown only this
  one time. You can switch it off with your password – unless one of your
  roles requires this login. Then after logging in you go straight to the
  setup and cannot do anything else first. Lost your phone and codes? An
  administrator resets them, and you set it up again. Wrong codes count like wrong passwords: after the set number of failed attempts the name is locked for a few minutes, in the API as well.
- **Sessions:** where you are logged in – browser, address, when last
  active. A session you do not recognise you end here ("End" or "End all
  other sessions") – and change your password.
- **"Your login details were changed"**: if the e-mail
  address of your account changes, this mail goes to the **previous**
  address; if your password changes – by you, after a one-time password,
  through the "Forgot your password?" link or because an administrator
  sets a one-time password –, to your **current** one. This also holds
  when an administrator or the import of people changed the address. The
  mail says what changed and when, gives your username and – if it was not
  you – "Changed by: …". If it was not you: after a new e-mail address,
  tell the administrators at once; after a new password, set one of your
  own at once with "Forgot your password?" (the link is in the mail) and
  tell them as well. A new account and the first password get no mail.
- **Notifications:** what you are notified about – in Rentalars, by e-mail
  and in the companion app on your phone, per kind – every
  single kind, also the AI's finished task (section 15). When and how far
  ahead shortages are reported is set for the whole company: Settings →
  Notifications (section 16); anyone who may read the settings gets there
  through the note on the page.
- **"Language":** whether Rentalars speaks English or German to you –
  pages, mails and notifications for you and the PDFs you download for
  yourself, such as the timesheet ("Save language"). "As the installation"
  takes the language your server sets. In English, dates appear as
  16/10/2026, times on the 24-hour clock and numbers with a decimal point
  (1,234.50); you type entries in the same format. The documents for
  customers have the language set for the company (section 16, "Company
  data and settings"). The login page follows the language of your
  browser.
- **"Tasks in the background"** (button at the top of the page): the large
  jobs you have started in the last few days – imports, lots of labels, a
  data export –, with status and the result to download (section 16).
- **API tokens:** including the token with which the Rentalars app on your
  phone works (below). If you revoke it here, the app can no longer reach
  Rentalars; you log in to it again. The list of your tokens
  turns into one card per token on a narrow screen, so that it does not
  push the page wider than the phone.

### The Rentalars app for Android

For working **without a network** – packing in the warehouse or in the
lorry, times at the venue – there is a companion app for Android phones
(Android 8 and later): **Rentalars Companion**, the companion app for
short. Everything else stays in the browser; the app talks to Rentalars via
the interface (section 16, "API tokens"). It is not part of the Rentalars
package but is **delivered separately**: your administrator knows where you
get it from and how it gets onto the phones. It needs Rentalars to be reachable via https with a valid certificate.

**What it can do:**

- **Packing lists without a network.** The app loads the packing lists of all
  projects with the status "Confirmed – details open", "Confirmed" and
  "Out" that you are allowed to see. In them you tick off as in the
  browser – packed as long as a row has not been issued yet, returned as
  long as material is out –, with the same limits and the same rights:
  anyone who may only read packing lists – for example with the Freelancer
  role – only sees them in the app. With the Crew role you pack in your own
  projects, also without a network, 1:1 as the packing list
  says (section 10, "Packing with the Crew role"); a quantity above the
  packing list is refused at synchronisation, your other ticks arrive.
  Anyone who only sees their own deployments
  sees no customer there. **Issuing** and **"Book the return"** remain a
  step in the browser (section 10).
- **Times without a network.** A stopwatch on the phone and times entered
  afterwards, on the projects and job functions you can also book to in
  the browser (section 13) – Rentalars also offers it the open
  service cases and your deployments with phase and times for this. The
  same rules apply: no times in the future, no overlaps. Whatever Rentalars
  rejects, the app shows with the reason.
- **Synchronisation.** As soon as the phone has a network, the app sends
  what has changed by itself – even when it is closed –, and immediately if
  you wish. It shows when it last synchronised and how many changes are
  still waiting. If someone else has ticked off the same row in the
  meantime, the **more recent** change applies, separately for "packed"
  and "returned"; if the time is the same, Rentalars wins. If your phone's
  clock is fast, a time in the future counts as "now" – your changes still
  keep their order among themselves. Every change and every time arrives
  exactly once, even if the connection drops along the way. From the next
  app version onwards the following also applies: if someone changed the
  row after your phone loaded it, Rentalars does not silently take over
  your change but reports that it has been changed on the server in the
  meantime and what it now says there. You see the Rentalars status and
  tick off again if yours is right.
- **Every confirmed project has its packing list** from the start – so the app
  finds it even if nobody has opened it in the browser yet.
- **Notifications on the phone.** You choose under My account →
  Notifications in the "In the app" column which notifications the app
  should show on your phone (section 15, "Notifications"). Rentalars
  remembers the choice and passes it to the app with every notification;
  how the app shows them is up to the app.
- **Projects and service cases without a network.** Rentalars
  remembers for every field of a project and of a service case when it was
  last changed – in the browser, in the app, by an automation or an
  import. If you change name, venue, times, notes, status or follow-up in
  the app without a network, at synchronisation the **more recent** change
  applies to each field: if someone changed the same field after you, their
  change stays; your other fields still arrive. If the time is the same,
  Rentalars wins; if your phone's clock is fast, its time counts as "now".
  If a status change is no longer possible by then – the project was
  cancelled, say –, Rentalars does not take it, and the app shows you the
  Rentalars status. For a service case, what it is waiting for and the
  follow-up belong to the status; they only arrive together. Older app
  versions change projects only with a network.
- **Names instead of numbers:** you see the project manager and the venue
  by name in the app, even if you only see your own deployments.
- **Your personnel data, absences and deployments.** In the app you see
  your personnel data as under "My area → Personnel data": phone, e-mail,
  what colleagues may see, your job functions (with rates only if you may
  see them) and your qualifications with their expiry date. You can change
  phone, e-mail and the sharing there, also without a network. As soon as
  the app is connected again, the more recent change applies: if you
  changed the same field in the browser in the meantime, the later change
  stays. You enter absences in the app or delete them; they are shown from
  30 days back. "My deployments" shows you all your deployments, past ones
  too, without cancelled projects.

Under My area → "My times" a small note points to the app; with × you hide
it for good.

**Logging in and security.** You log in to the app with your name and
password – and with the code from your authenticator app if you have set up
two-factor login. For this the app gets its own **token**, limited to
packing lists, projects, time tracking and
e-mail, valid for 30, 90 or 180 days; it
does not store your password. The token appears under My account → API
tokens and can be revoked there at any time – for example if a phone is
lost. A token like this cannot create further tokens and does not see any
other tokens of your account. Logging out in the app revokes the token and
deletes all of the app's data from the phone. The app requires a screen
lock and asks for it when opened, stores everything encrypted and does not
allow screenshots.

---

## 3. First steps after installation

In this order you get to a working system fastest. Each step is described
in detail further down.

1. **Enter your company data and logo** (Settings → Company data and
   settings). They appear on the packing list and on the documents. Before the
   first invoice is created, the bank details, register details, e-mail
   address, VAT ID or tax number and the payment term belong there too
   (section 11). If the warehouse is not at the company's address, enter
   the **"address of the warehouse"** – that is where the projects' trips
   start and end (section 7, "Schedule"). The same page holds the usual
   project times – 12:00 to 12:00 on the following day by default –,
   whether Rentalars writes the invoices ("use Rentalars as accounting software",
   section 11), and the **"language of documents"** for your customers –
   the language of the first-run setup is preselected (section 16). What
   the labels of the material show – logo, phone number, web address – you
   set under **Settings → Labels** (section 4, "Labels").
2. **Check categories, units and scale** (Settings → Categories and
   codes, Units, Rental scales). Supplied are the categories Sound (T),
   Lighting (L), Video/media (M), Rigging/truss (R), Cables (K), Sale (V),
   Material subrented from others (E), Event technology services (D),
   Customer material (C), Incidental costs (N) and Fleet (FZ)
   for your vehicles and trailers (section 4, "Fleet") – on an installation
   in German with their German names (Ton, Licht … Nebenkosten, Fuhrpark);
   the codes are the same. Subrentals end up in E – with the product E-001 "Subrental"
   –, D holds the service products of the personnel's job
   functions (section 12, "Job functions"), N transport, travel costs and
   fees (section 5, "Product kinds"); none of these three has stock of its
   own. C is for material that customers store with you (section 5,
   "Customer material"). You create surcharges on prices in a category of
   their own. A category's code becomes the beginning of the article
   numbers of its products – change it now, later it is no longer that
   easy. On top of that come the usual units and the "Standard scale"
   (section 16, "Master data").
3. **Create storage locations** (Settings → Storage locations), hall
   by hall, shelf by shelf – then the packing list can show the walking route
   through the warehouse. "Main warehouse" is supplied; it is
   preselected in the "New items" form until you make another storage
   location the default (section 4, "Storage locations").
4. **Take over material**: import the Excel list (Material management →
   Import), or create the first models by hand. Products, customers and
   personnel can also be taken over from a spreadsheet (section 16, "Import
   and export").
5. **Create products** and **assign the material**. Only then can it be
   planned. The list "Material management → Open points → Material without
   product" shows what is still missing.
6. **Create inspection types** (Settings → Master data → Inspection
   types) if material has to be inspected regularly – for vehicles e.g.
   the main inspection (HU) and DGUV/UVV –, and enter the last inspection
   from the paperwork (section 4, "Inspections"). For inspecting
   electrical devices after DGUV V3, mark the inspection type as an
   electrical inspection and enter the protection class on the models –
   then Rentalars asks for the measured values. For the short check in
   between – label there, velcro there? – there are the **audits**: check
   the interval and the quick picks under Settings → Audits (section 4,
   "Audits and to-dos"). If every piece has data of its own such as a MAC
   address or firmware, create **custom fields** for it (section 4, "Custom
   fields").
7. **Check job functions and their prices** (Personnel → Job functions).
   Supplied are Technician, Lighting technician, Sound technician, Video
   technician, Stagehand, Warehouse, Project planning and Other (in German:
   Techniker, Lichttechniker, Tontechniker, Medientechniker, Stagehand,
   Lager, Projektplanung, Sonstiges), each with its service product. The first-run setup asks for two values for them, both net:
   **"Price per hour for the customer"** (€45.00 proposed) and **"Internal
   costs per hour"** (€30.00). All eight job functions get this price on
   their service product and these costs as their guide value. Adjust them
   here for each job function on its own – with day rates and a higher rate
   beyond a number of hours (section 12, "Job functions"). If your
   installation has job functions without a
   price, enter the price per hour on every service product so that
   personnel in the project has a price. If night, Sunday and public
   holiday hours are to cost more, choose the federal state under
   **Settings → Surcharges**, check the rates and switch the surcharges on
   – initially they are off (section 16, "Surcharges").
8. **Create people** (Personnel → New person), give them job functions –
   their own hourly or day rates only where they differ from the
   function's guide value – and invite them. In doing so every person gets
   their login with the Crew role (freelancers: Freelancer). Anyone who may
   do more – project management, warehouse, office – gets the appropriate
   role under Settings → Users (section 12, "People", and section
   16).
9. Create an **internal project** ("Lager und Werkstatt", warehouse and
   workshop) to which times without a customer project are booked.
10. **Set up the mailboxes** and the **signature** (Settings →
    Mailboxes and signature) so that mails with the project tag land in
    the project (section 14) – and so that the crew can answer deployment
    requests by reply mail (section 12, "Requests: acceptance or
    refusal"). If every new inquiry is to receive an acknowledgement of
    receipt straight away, you create an **automation** for it (section
    16, "Automations").
11. **Set up two-factor login** for yourself (My account) and require it
    for all administrators (Settings → Company data and settings) –
    at the latest before Rentalars can be reached from the internet. A look
    at the **Self-check** (Settings) shows what else is missing, and
    "Backup and encryption" whether the nightly backup is running.
12. **Create frequent venues** (Customers → Venues), with access, power and
    site plan/hall plan.
13. **Look through the document templates and text blocks** once
    (Settings → Document templates, Settings → Text blocks):
    headings, introduction and closing texts, your rental terms. If you
    write to customers in English, "Template texts in English or German"
    takes over the English texts (section 11, "Templates and text
    blocks").
14. **Set up accounting** if invoices are to go to Lexware Office or as a
    DATEV file to your tax adviser (Settings → Accounting, section
    16) – the DATEV details are best worked out together with your tax
    adviser. If you write the invoices in another program, untick "make
    invoices in Rentalars" under Company data and settings instead (section
    11).
15. **Create the first customer and the first project.** For formats that
    keep recurring, you then save a project as a **template** (section 7).
    For rentals where the customer collects the equipment themselves, the
    template **"Dry Hire (rental without crew)"** (in German "Dry Hire
    (Vermietung ohne Personal)") is already in place (section 7, "Dry hire
    – rental without personnel").

To try things out without risk, you can have example data created during
the first-run setup – ideally in a test installation of its own.

---

## 4. Material

"Material" is everything that stands in the warehouse and has a sticker
(or, for consumables, is counted).

### Model and item

A **model** records what is the same for all pieces: article name, short
name, category, manufacturer, description, weight, dimensions and power, the protection
class (below, "Protection class"). An **item** records what
makes the individual piece: ID, serial number, where it was bought
("Bought from") with invoice number, invoice date and purchase price,
condition, storage location, note.

Under "Material management" the **Models** tab shows the models with the
number of their items. The **Items** tab shows both together, one row per
item – like the previous Excel list with its 13 columns; you show further
columns via "Columns" (section 2, "Lists").

**An item's page** has the buttons "Report defect", "Label" (below,
"Labels"), "Duplicate" (below, "Duplicating") and "Edit item"
at the top and five tabs below them:

| Tab | Content |
|---|---|
| **Item** | the data, beside them (before, at the top) the narrow box "Photos" (below, "Photos and files"), for a vehicle the box "Vehicle data" (below, "Fleet"), the boxes "Custom fields" (below, "Custom fields") and "Audit and to-dos" (below, "Audits and to-dos"), for everyone who sees the reports the box "Earnings" (below, "What an item earns"), below them "Change status", "Installed in / contains" (with "Install in" and "Add an item"), blocked periods, the box "Calendar link" (below, "Calendar link"), the box "Built-in bulk material" (below, "Built-in bulk material") and – for everyone who may see purchase prices – the box "Asset accounting" (below, "Fixed assets, depreciation and book value") |
| **Timeline** | when the item and its product are booked – only with the special right "See availability of material" (section 16, "Roles and rights") |
| **Inspections** | what is due when, the previous inspections – for an electrical inspection with measured values and "Test report (PDF)" –, "Record an inspection" |
| **Files and defects** | invoice, manual, inspection protocol; the defect reports with photo and their service case |
| **History** | every change, every installation and removal, every project; the individual changed fields collapsed |

The data show the **model** next to category, manufacturer,
product and serial number – a click leads to its page.

Next to the status, notes that should not be overlooked appear at the top:
an overdue inspection or one due soon ("never inspected" if there has not
been one yet) and – on a rack or case – a problem with a part inside it
("0815 inside is defective", "0815 inside: inspection overdue"). Every tab of the item also shows **"Audit due"** and **"2 to-dos"**
there; a click leads to the box "Audit and to-dos" (below, "Audits and
to-dos").

**A model's page** has the tabs **Model** (the data, the inspections that
apply to the model, the box "Earnings", the list of its items
and the box "Calendar link"), **Timeline** (as on the item,
only with the special right "See
availability of material") and **Files**. At the top are "New items",
 **"Enter a purchase"** with this model in the first row
(below, "Entering a purchase"), "Edit model", **"Duplicate"** and
**"Labels"** for all items of the model (below, "Labels").

**Opening an item by its ID**. In the head of every tab of
the material management – products, models, items, fleet, "Open points",
inspections, audit, import – there is the field **"Item ID"**. Type the
ID as it is on the label or as you copy it from a list – `0427`, `427` or
`#0427` – and press Enter or "Open": Rentalars opens the item, a retired
one too. If there is no such ID, Rentalars says so and shows the list of
items, filtered by what you typed. The field is there for everyone who may
read the material. It takes everything a label's code can
hold – and has a **"Scan"** button next to it (below, "Scanning labels and
codes").

If the material belongs to a customer, **"Owned by …"** with the
customer's name appears at the top of the model's and the item's pages
(section 5, "Customer material"). Inspections, defects, blocked periods
and labels are available for it just as for your own material.

### Creating new material

1. **Material management → Models → New material model.** Article name and
   category are required.
   - **Manufacturer:** type; Rentalars suggests known manufacturers. If it
     does not exist yet, simply type the name out in full – the last
     suggestion then says "new manufacturer" –, and it is created together
     with the model.
   - **Product:** likewise, choose from the suggestions by article number
     or name which product the model belongs to. This can also happen
     later; left empty, the model cannot be planned yet (below, "Assigning
     material to a product").
   - The **short name** appears in lists and on the labels; left empty, the
     article name is used.
   - Under **"Weight, dimensions and power"** you enter weight, power and
     the dimensions (below).
2. On the model's page: **New items.** Enter the **number of items**; they
   get consecutive IDs and share the purchase data:
   - **Start ID** – left empty, Rentalars assigns the next free IDs. If you
     enter one, the first item gets this ID and each further one the next
     free one after it. If the start ID is already taken, Rentalars says
     so.
   - **Serial numbers** – one field for each item, in the order of the IDs;
     if you increase the number, fields are added. Enter takes you to the
     next field – handy with a hand scanner that sends Enter after each
     number –, and several pasted lines fill the following fields (and
     increase the number if necessary). An empty field leaves its item
     without a serial number. **If a serial number exists already** – on another item, of whatever model, also a retired, sold or
     lost one; upper and lower case and spaces at the ends do not count –
     or you type it twice into the form, Rentalars warns after the first
     save ("The serial number 4711 exists already: item 0042 (model …)."); with the box
     **"Create anyway"** you create the items. The same holds for "Enter a
     purchase", editing and duplicating an item (there "Save anyway", and
     only if you changed the serial number), for the import (the preview
     names every row; from 100 rows a summary) and for the API
     (`warnings`). It is never forbidden – some makers issue numbers twice.
     Without JavaScript it is one field with one serial number per line.
   - **Storage location** – the default storage location is preselected
     (below, "Storage locations").
   - Under **"Purchase"**: **"Bought from"** – type and choose from the
     suggestions; a new supplier is created together with the items –, the
     "Supplier's article number", **invoice number**, **invoice date**, purchase price and purchase note.
     Rentalars suggests the supplier and the supplier's article number from
     the most recently created item of this model – the second delivery of
     the same cable usually comes from the same supplier.

   Under "Edit item", "Bought from" with suggestions and the invoice number
   are available in the same way.

**Net or gross**. If the invoice shows the gross price, you
need not work it out yourself: below the purchase price you choose "net"
or "gross" under **"The price is"** and, for gross, the tax rate under
**"The gross price includes"** (the standard tax rate is preselected).
The price is always stored net, rounded to cents – €119.00 gross at 19 %
becomes €100.00. This is available in "New items", in "Edit item" and in
"Enter a purchase", only with the right "See purchase prices". Rentalars
remembers your last choice for the next form.

**A new supplier with its master data**. If you type a name
under "Bought from" that does not exist yet and choose the suggestion
**"new supplier"**, a window "New supplier" opens: name (already filled
in), contact, "Our customer number there", e-mail, phone, address and
note. **"Save supplier"** creates it and puts it into the field; what you
have already entered in the form below stays. The window does not accept
a name that already exists. It is there for whoever may edit the material
or the settings. Without JavaScript – or if you simply leave the new name
as it is – Rentalars creates the supplier as before when saving, with the
name only.

**Purchase date not known exactly**. Of an old item you
often know only the year, or the month. In the field **"Invoice date"** of
"New items" and "Edit item" you may therefore type `00.00.2015` (year only),
`00.05.2015` or `05.2015` (month and year), or just `2015`; a full date with
a two-digit year such as `12.05.15` works too (00 to 68 mean 2000 to 2068,
69 to 99 mean 1969 to 1999); in English
`00/00/2015`, `05/2015` and `2015`, and `2015-05-00` and `2015-00-00` work
as well. Rentalars shows it as you know it – "2015" or "05/2015" instead of
a full date – on the item and on the model, in the lists, in the exports and
in the audit mode's master data. Internally the first day of the period is stored, so
that such an item sorts before the dated ones of the same year; the
depreciation (below, "Fixed assets, depreciation and book value") starts
with January of a year known alone, and with the month if the month is
known. A day without a month ("12.00.2015") is refused, and so is a year
outside 1900 to 2999 – this catches a typing error such as 215. The import
of the Excel list (below) takes these forms too, and the interface likewise
(`purchase_date` as `2015-00-00`, with the read-only `purchase_date_precision`
"day", "month" or "year"). "Enter a purchase" and the incoming invoices
(section 11) work with the complete date of the invoice.

### Entering a purchase

A delivery of ten cables, four spotlights and a wireless set on one
invoice? You enter it in one step: **"Enter a purchase"** is
at the top of Material management → Models and → Items, also
→ Products (there instead of the button "Import"), and on a model's page –
there the model is already in the first row. It needs the right to edit
material.

1. **Invoice** (optional): choose the invoice file. When you save, it is
   attached to every new item as a file of the kind "Invoice" – it is
   stored only once. **"Read the invoice"** fills in the form from it
   (below); "Remove the invoice" takes it away again.
2. **Purchase**, once for all: **"Bought from"** (an existing or a new
   supplier, above), **invoice number**, **invoice date**, with the right
   for purchase prices **"The prices are"** net or gross with the tax rate
   (above, "Net or gross"), the **start ID** – empty: the next free IDs –
   and a **purchase note** for all items.
3. **Positions**, one row per model: **model** – type and choose an
   existing one, or type the name of a new one; then "New model: category,
   manufacturer, product" opens, and the category is required –, **number
   of items**, **price per piece**, **storage location**, **supplier's
   article number**, **serial numbers** (one field per item, as in "New
   items") and **"Bought as a set"** – then the price is that of all
   pieces together, and the first item gets it. For bulk material the row
   becomes a stock row with the number as its quantity. The
   form starts with **one** position; **"Another position"** adds one at a
   time – without JavaScript the button sends the form, and everything
   entered, the chosen invoice included, stays. The AI's proposal adds a
   row per position of the invoice (below). Rentalars ignores empty rows;
   at most 100 positions per purchase. You may type the purchase price
   with thousands separators ("1,072.50"; in German "1.072,50").
4. **"Create items".**

**The sum to check against**. Below the positions is
**"Sum of the positions:"** net and gross, with the tax rate used – price
times number, a set price once; computed while you type and again after
every submit. A position without a price counts as 0, and the line below
says how many there are. With prices entered gross, the gross sum is the
sum of your prices and the net sum what Rentalars stores (each price net,
rounded to cents); with net prices Rentalars computes the gross sum once
with the tax rate, as an invoice does. If "Read the invoice" found its
total, **"Invoice:"** shows it net and gross next to it with the
**difference** – gross when both gross sums are known, otherwise net – or
"matches". Shipping, discounts and deposits of the invoice are no
positions and may explain a difference. Only those with the right "See
purchase prices" see the sums.

Rentalars creates all items in one step, with consecutive IDs across all
positions – or, if something is wrong, none at all, and says in which row.
Then **"Purchase entered"** shows the new items with ID, model, serial
number, storage location and purchase price; **"Print labels"** leads to
the "Labels" page with exactly these items (below), "Enter another
purchase" to the next one.

**Read the invoice.** Only a **PDF with text** is read – a scanned invoice
is not, as there is no text recognition; a photo or scan is attached all
the same. What "Read the invoice" fills in depends on whether **"Reading
invoices"** is switched on under Settings → AI (section 16, "AI"):

- **Without AI** Rentalars finds the invoice number, the invoice date, a
  supplier it already knows and the totals of the invoice (net
  and the amount to pay). You enter the positions yourself.
- **With AI** the AI also reads the positions in the background – model,
  number, price, article number and the **serial numbers** the
  invoice lists. For a new model it proposes **category** and **product**
  from your existing ones. You can go on typing meanwhile. When it is
  done, Rentalars shows what it found – "Found: 3 positions · invoice
  RE-2027-118 · total €1,276.28 gross" –, and **"Fill in the AI
  proposal"** enters it into the
  form; nothing is saved before "Create items". The result is marked "made
  by AI". If the AI did not succeed, the button reads "Fill in what was
  found" and enters what Rentalars found without AI.

Either way it is a **proposal**: it fills only empty fields and adds rows;
what you typed stays. Rentalars matches suppliers and models against the
existing ones – but it fills in a model only where the match is certain;
otherwise "Perhaps:" below the row names the models that may be meant, to
click. The same for category and product of a new model: Rentalars fills
them in only if the AI names an existing category (by its path, its code
or a name only it has) or an existing product of your own (by its article
number or a name only it has) exactly – Rentalars never proposes customer
material for a purchase, nor takes it there –; otherwise the field stays empty and a hint at
the row names the proposal ("The AI proposed the category “Lighting >
Floods”, which does not exist: choose the category yourself."). Serial
numbers that are not in the text of the invoice are left out, and
Rentalars says so. Rentalars reads the **amounts** itself, as the invoice
prints them – "1,072.50", "1.072,50", "€1,072.50" or "1.072,-"; whether
"1.072" means one thousand and seventy-two or one euro and seven cents is
decided by the other amounts, the text of the invoice, its currency and
its language, and every amount is checked against the amounts in the
text. If an invoice
is too long for the AI, the proposal says that its end was not read; you
then enter the last positions by hand. Every row that
comes from the invoice is marked "from the invoice" with what it said
there and has to be confirmed with the box **"Checked"** before Rentalars
creates anything.

Rentalars keeps an uploaded invoice for the purchase for two days, only
for you; if the purchase is not saved, Rentalars deletes it by itself
afterwards. The interface does the same (section 16, "API tokens").

**Invoices that arrive by the dozen.** If you want to keep every supplier
invoice, spread its freight over the goods and have the items classified as
low-value or fixed assets right away, there is **Accounting → Incoming
invoices** (section 11, "Incoming invoices"). Its "Book in
goods" uses the same checks as "Enter a purchase".

### Duplicating

You create similar material with **"Duplicate"**:

- **On a model** it opens "New material model" with all values of the
  original – the name with "(copy)", the category with its fields,
  manufacturer, product, description, weight, dimensions and power. If
  inspection types apply to the original itself, the form offers: **"The
  copy gets the inspection types of the original, too: …"**. Items and
  files stay with the original. Nothing is saved before the form's button.
- **On an item** it opens "New items" for the same model, filled in with
  supplier, supplier's article number, invoice number, invoice date,
  purchase note and storage location, status "available" – without ID and
  serial number. It takes over the purchase price only with the right "See
  purchase prices", and not from an item bought as part of a set.

Whoever may create material may duplicate it. Products are duplicated
the same way (section 5, "Creating a product").

**Bought as a set.** If several items come together for one price – a
wireless set of transmitter and receiver, a case with its contents –, the
purchase price is noted at one item, say `0851`; the others have none of
their own. If you create them together, tick **"The price is that of all
these items together (a set)"** under "Purchase": the first item gets the
price, the others have it included in the first one. Afterwards, enter the
ID of the item with the price under "Edit item" in **"Price included in
(ID)"** (empty: bought alone). The item's page then shows "included in the
price of 0851" at the purchase price and, under **"Bought as a set"**, all
IDs of the set, the one with the price first. In the list of items the
column "Purchase price" shows `#0851` instead of an amount – so does the
CSV file, and the import reads it back the same way (below, "Taking over
the Excel list"). Only those with the right "See purchase prices" see and
change purchase prices.

**The ID** is a consecutive number, written with at least four digits:
`0001`, `0002`, … and after `9999` it continues with `10000`. Rentalars
assigns the next free one. If the pieces already have stickers, you enter
the ID of the first one as the start ID (above).

**The category-specific value** is the one property that matters in a
category: for cables the length, for trusses the dimension. What the field
means is set by the category (section 16).

**Further fields per category.** A category can have more than one
property – for spotlights, say, light source, beam angle and "DMX yes/no".
Every field has a type: text, number with unit, choice or yes/no. They are
created in the settings on the category (section 16). Power is not a
field of the category: every model has it as a field of its own (below).
The further fields appear under "Edit model" as soon as the model has been
saved once. Rentalars checks the input: a number field takes a number,
"12.5" or "12.5 m".

**Differing on the item.** A single piece can differ from its model – the
modified cable is 7 m long instead of 10 m. For this, under "Edit item",
each field of the category and the item's own description show what the
model says ("Empty: as the model – 10 m"). Left empty, the model's value
applies; a value of its own is marked "own" on the item's page.

**Weight, dimensions and power** you enter on the model, in the "Weight,
dimensions and power" box of its form: weight in kg, the power of one piece
in watts ("Power (W)"), length, width and height in cm. From the dimensions
Rentalars calculates the volume; from that and from the weight the packing list
adds up the weight and volume of a load (section 10).

**Protection class**. For an electrical device you choose
the **protection class** in the same box: "I (protective conductor)", "II
(protective insulation)" or "III (safety extra-low voltage)" – "–" for
anything that is not electrical or whose class you do not know. It applies
to all items of the model. If one piece differs, say after a modification,
you choose another under "Edit item", box "Different from the model", at
**"own protection class"** ("Empty: as the model – …"); the item's page
marks it "own". The same class as the model is no class of its own:
Rentalars empties the field when saving. The protection class is shown
with the data of model and item, as the column "Protection class" in the
lists of models and items (via "Columns"; for an item its own, else the
model's), in the master data of the audit and in import and export (below,
"Taking over the Excel list"); "Duplicate" takes it over. The electrical
inspection starts from it (below, "Inspections").

### Custom fields

Some details belong to every piece on its own: the MAC address of a
network device, the firmware version of a console, the insurance value of a
camera kit, the inspection sticker. For these there are,
**custom fields**, grouped into **fieldsets**; a material
model gets one fieldset, and each of its items has its fields with a value
of its own.

**Rule of thumb:** the **category-specific fields** (above) describe the
**model** – the length of a cable is the same for every piece, and only a
modified piece gets a value of its own. **Custom fields** describe **the
single piece** – MAC address, firmware, insurance value: every item has
its own value.

**Creating fields:** Settings → **Custom fields**, "New custom field":

- **Name** – also the heading of its column in lists, exports and imports;
  each name only once.
- **Type** – text, long text, number with unit, date, yes/no, choice list,
  web address or e-mail address; for a number the **unit** ("m", "W",
  "kg"), for a choice list the **options**.
- **Check pattern** – optional: a regular expression every value must
  match, e.g. `^[0-9A-F]{2}(:[0-9A-F]{2}){5}$` for a MAC address (for text,
  long text, number, web and e-mail address). So that checking a value
  cannot take minutes, Rentalars refuses when saving: nested repetitions
  whose count can vary, such as `(a+)+` or `(.*,){5}`; alternatives inside
  an open-ended repetition, such as `(ab|cd)+` – with an upper limit,
  `(ab|cd){1,5}`, it works –; back-references such as `\1`; and patterns
  of more than 200 characters. A fixed count inside is allowed, like
  `(:[0-9A-F]{2}){5}` in the example, and so is a small bounded one such
  as `([0-9]{1,3}\.){3}`. The message says each time how to do it
  differently.
- **Help text** – shown below the field in the form.
- **"choosable as a column in lists"** – the item list offers the field as
  a column (below).
- **"unique"** – no two items may have the same value, e.g. a MAC address.
- **"only with the right to see purchase prices"** – the values are shown,
  searched, exported and changed only by those with the right "See
  purchase prices", also in the history and the API; on the item's page
  the field carries the badge "confidential". For an insurance value, a
  leasing contract or a PIN. If you tick it on a field that already has
  values, its earlier values disappear from the history of the items and
  from the change log as well for everyone without this right.

If items already have a value, Rentalars takes a new type, other options,
a check pattern or "unique" only if every stored value fits them;
otherwise it names the values that do not fit. A check pattern checks
values of up to 4000 characters – the longest a long text may be –; it
refuses a longer value. If checking a value takes too long all the same
(more than half a second), Rentalars refuses the value with "Check pattern
too complex: checking the value of the field … took too long. Please
simplify the pattern under Settings → Custom fields." – in the form, in
the import and through the API. A check pattern saved before this check
keeps working until someone edits the field; then it has to meet the
rules above. A field with values is
deleted under "Delete custom field" only once you tick "Delete the values
of … items, too"; the history of each item keeps them.

**Fieldsets:** Settings → **Fieldsets** (or the tab next to it), "New
fieldset": name, description and below it every field – tick what belongs
to the fieldset, set the order in the forms and on the item's page with
the **position**, and tick **"required"** per field where a value must be.
A field can be part of several fieldsets. A fieldset a model has cannot be
deleted; without models only it goes, fields and values stay. Fields and
fieldsets are seen by those who may read the settings, created and changed
by those who may change them, deleted by those who may delete there – as
for categories.

**Giving a model a fieldset:** in the material model's form, box **"Custom
fields of the items"**, under "Fieldset" – or "none". Duplicating takes it
over. On the model's page it is listed with the data under "Custom
fields", with its fields; required fields carry the asterisk.

**Entering values:** "New items" and "Edit item" have the box **"Custom
fields"** with the fields of the fieldset. A required field needs a value
when you create or edit **one** item. If you create **several at once**,
the values apply to every new item, and required fields may stay empty – a
MAC address is a different one for each piece –; a unique field does not
appear at all then. "Enter a purchase" asks for no custom values;
afterwards Rentalars names the new items that lack a required value, each
with a link to its form. Duplicating takes over all values except those of
unique fields.

The item's page shows the values in the box **"Custom fields"** in the
order of the fieldset, with "A required value is missing: …" above them
while something is missing. A web address is a link there and in the
list if it starts with `http://` or `https://`, an e-mail address if it
is valid; any other value is shown as text. Every change is in the history. If the model
gets another fieldset, the values stay: values of fields no longer part of
it are listed collapsed under "Values of fields no longer in the fieldset"
and show again as soon as the field belongs to the fieldset again.

**In lists, search, import and export.** You show fields marked
"choosable as a column in lists" under Material management → Items via
"Columns"; they sort as numbers, dates or text, are in the CSV file, and
under "Filter" each has a search field of its own. The search field of the
items and the search in the sidebar also find an item by the values of its
custom fields – never by those of confidential fields. The material import
reads columns headed with the name of a field, and the export in the
import format writes them (section 16, "Import and export").

### Photos and files

**Photos**. The page of a model and the page of an item have a narrow box **"Photos"** beside the data, below it on a narrow screen. With the field and
**"Upload"** you add one or several photos at once (up to 20; on the phone the camera opens if you wish); the photos stand side by side
as previews, a click opens the photo in full size, **"remove"** deletes it after a question. The photo uploaded first is shown in the head of the
page. An item shows its own first photo, else that of its model, and lists the photos of its model under its own. Whoever may only read
the material sees the photos and does not change them.

Rentalars does not keep a photo as it came but **makes it anew**: turned upright, as a JPEG, at most 2048 pixels on the long side –
this saves space –, and a small preview. Of the details of the camera **only the place of the shot** (GPS: latitude, longitude,
altitude) stays; device, time, direction and comment are removed. Whoever downloads or passes on a photo passes on the place. The same
goes for photos in the chat, on defect reports and on expense receipts. **Documents** – PDF files, the copy of an invoice, project files, mail
attachments – stay as they came; a picture stored as a manual, protocol or other file is made anew like a photo. Older pictures in the "Files" tab are shown in the box (without a preview; they are
delivered whole).

**Files.** On the model (**Files** tab) and on the item (**Files and defects** tab) documents can be stored: "Add a file", choose the
type – manual, invoice, inspection protocol or other –, a label if you wish, "Upload". Manuals and data sheets belong to the model,
the invoice for a single purchase to the item. The item also shows the files of its model.

### Bulk material

Gaffer tape, cable ties, lamps: things nobody labels one by one. On the
model set "Stock is kept as" to **bulk quantity**. Instead of many items
there is then one row with a quantity ("New stock row").

### Storage locations

Where something is kept appears on the item in the **"Storage location"**
field. The storage locations form a tree under Settings → Storage
locations: hall, inside it shelves, inside those compartments – a case that
always stands in the same place can also be a storage location. Every
location names what it is **"part of"**; Rentalars then writes it with the
whole path: "Halle 1 > Regal A > Fach 3".

The list of items can be filtered by storage location. The packing list can
sort by storage location and so gives the walking route through the
warehouse (section 10).

**The default storage location.** One storage location can be the default
for new items: the "New items" form suggests it. A new installation comes
with "Main warehouse" as the default. You set which one it is under
Settings → Storage locations with the **"default for new items"**
tick box; there is at most one, and a deactivated storage location cannot
be it. The Settings page names it next to "Storage locations" ("New
items go to Main warehouse"). The import and the API do not set it by
themselves.

**Installed material is where its device is.** If a radio receiver sits in
a rack, the rack's storage location counts; the receiver's page adds
"(where its container is)". If the rack moves, nobody has to move the
receiver in the system.

**The storage spot.** Within a storage location an item lies at a spot –
"shelf 3, second compartment, third place". Every item has a
short field **"Storage spot"** (up to 12 characters) for it, in the item's
form and when creating new ones. The usual short form is **"03-A-2"**: a
two-digit number, a letter, a digit. You need not type it exactly: "3a2",
"3 A 2" and "03.a.2" are turned into "03-A-2" by Rentalars; other short
text stays as you write it. It is a text field, not a list of spots that
somebody would have to maintain – nothing more is needed, and search and
import manage with it.

The spot shows on the item's page after the storage location, in the item
list in the "Storage location" column ("Hall 1 03-A-2"; sorted by location
and spot), in the lists of inspections and audits and in the audit mode.
Search finds it ("3a2" is enough), bulk editing sets it for all chosen
items (below), the import knows the column **"Storage spot"** and the
export writes it, duplicating copies it, and the interface calls it
`storage_spot`. On the packing list it stands next to the chosen item that
has not been issued yet – so you find it when packing. An installed item
shows the spot of the one it sits in. If bulk editing moves an item to
another storage location, its old spot is dropped unless you name a new
one.

### The condition of an item

On the item's page, under "Change status" – right below the data, before
"Installed in / contains":

| Status | Meaning | Counts towards stock? |
|---|---|---|
| available | in the warehouse, ready for use | yes |
| in use | currently out with a project (Rentalars sets this itself on issue) | yes |
| defective | broken, not yet being worked on | **no** |
| in repair | at the service | **no** |
| blocked | must not go out, e.g. not inspected | **no** |
| retired, sold, lost | no longer there | **no**; disappears from the everyday list |

Setting an item to "defective" takes it out of planning immediately: the
availability of all projects reckons with one piece fewer – and shows a
shortfall where applicable.

**The reason.** With every status change Rentalars asks for the reason. For
"defective" it is required – "fan sticks", "display cracked" –, otherwise
optional. The reason appears on the item as long as the status applies and
stays in the history.

**There are only three ways out of "defective":** in repair, retired or
sold. A defective piece cannot simply be set back to "available" – only
from repair. That way no defect disappears from the list unnoticed.

Retired, sold and lost items are kept with their history. You find them
via the status filter of the material list.

For a defect there is a shorter way with a photo ("Report defect"), for a
repair with a fixed end the blocked period – both follow straight away.

### Report defect

Made for the phone in the warehouse: **"Report defect"** at the top of the
item's page (quickest via the QR code on the label, see below).

1. Under **"What is defective?"** describe what is wrong – "plug loose".
2. A **photo** with it if you wish. On the phone the camera opens.
3. "Report defect".

The item is then set to "defective", with the description as the reason,
and the warehouse receives a "Defect reported" notification (everyone who
may change material). If the item is already defective, the report is
added – a second fault is good to know about too.

**The report becomes a service case.** The automation
**"Defect report → service case"** (in a German installation
"Defektmeldung → Servicefall") makes a service case of every report at
once – with a title such as "Defect 0042 SM58", with what is defective and
with the photo among its files. For your own material the case is
internal; for customer material it belongs to the customer (section 7,
"Service cases"). Whether and how this happens, an administrator sets
under Settings → Automations; instead of the case, the report can first
wait under Projects → Inquiries (section 16, "Automations").

All reports appear on the **"Files and defects"** tab under "Defect
reports": when, by whom, in what context (such as "Return of 2026-0042"),
with photo – and with their service case and its status. If a report has
none yet, **"As a service case"** makes one of it (with the right to
create projects). One report makes at most one service case. Defects you
notice on return you report directly on the packing list (section 10).

### Blocked periods

A device is in repair at the manufacturer's from 3 to 14 April? Instead of
switching the status back and forth by hand, you enter on the item's page
under **"Blocked periods"**: **From**, **Until** and the **Reason** ("in
repair at the manufacturer's"), then "Block".

During this period the item does not count towards stock: its product has
one piece fewer, and a project that needs it shows a shortfall there where
applicable. Before and after, it can be planned quite normally. "lift"
ends a block early. Blocked periods appear in the timeline.

The difference from the "blocked" status: the status applies until someone
changes it. A blocked period only applies for its period and ends by
itself.

### Inspections

Electrical inspection, visual inspection of lifting accessories, the
statutory accident-prevention (UVV) inspection of chain hoists – whatever
has to be inspected regularly, Rentalars manages too.

**Inspection types** are under Settings → Master data → Inspection types
(section 16): name, **interval (months)**, a description and which
**categories** and **material models** they apply to, the box
**"electrical inspection (DGUV V3 / DIN VDE 0701-0702)"** (below). An
inspection type on a category applies to all items of all models in it,
subcategories included.

**When is an inspection due?** Rentalars works it out:

- **Next inspection = last passed inspection + interval.**
- A **failed** inspection sets the item to "defective"; it is due again
  immediately and is inspected anew after the repair.
- An item that has **never been inspected** counts as **overdue**. "We
  don't know" is not "OK". So a new inspection type initially makes all
  its items overdue – until they have been inspected or the last
  inspection has been entered from the paperwork.
- **Due soon** is whatever becomes due in the next 30 days.

**Recording an inspection:** the item's **"Inspections"** tab, "Record an
inspection": inspection, date, "Inspected by", result ("passed" or
"failed"), note and, if you wish, the **protocol** as a file, "Record".
The **date** (today) and "Inspected by" (you) are already filled
in – change them if somebody else inspected or you enter it later. At
the top of the tab, for each inspection type, it says when it was last
inspected and when the next one is due – red overdue, yellow due soon,
green OK. Below that the previous inspections with their protocols.

**Electrical inspection after DGUV V3**. If an inspection
type is marked as an electrical inspection and you choose it when
recording, the box **"Electrical inspection (DGUV V3 / DIN VDE
0701-0702)"** appears below date and "Inspected by" – with the checks in
the order of the standard:

- **Protection class** (required) – filled in with the item's (above,
  "Protection class"); the limits depend on it. **Cord length (m)** –
  filled in from the category-specific value "Länge"/"Length" (in m, cm or
  mm, the item's own first); empty counts as up to 5 m. The **test
  device** ("Benning ST 760, SN 12345") starts with the one you entered
  last.
- **Visual inspection** (required; a tick box **"Visual
  inspection passed"**): ticked means passed, unticked not passed – then
  Rentalars suggests "failed".
- **Protective conductor resistance R<sub>PE</sub> (Ω)**, **insulation
  resistance R<sub>ISO</sub> (MΩ)**, **protective conductor current
  I<sub>PE</sub> (mA)** and **touch current I<sub>B</sub> (mA)**. Next to
  each field is its **limit**, for R<sub>PE</sub> with the cord length it
  applies to, and as soon as you type a value "within the limit" (green)
  or "outside the limit" (red). What is not measured for the protection
  class shows as "Only for protection class I" and stays empty; a value
  you did not measure you leave empty as well.
- **Function test**: "passed", "not passed" or **"does not apply"** – for
  a cable, say.

Below is the **suggested result** with its reasons: "passed" when the
visual inspection passed, what the protection class needs is measured
(below), the function test did not fail and every value entered is
within its limit; otherwise "failed", for instance with "RPE 0.52 Ω is
outside the limit ≤ 0.3 Ω." If a needed value is missing, that is a
reason too; in the list of inspections and in the test report its "not
measured" is then shown in red. Rentalars checks the values while you
type, without JavaScript when you send the form. You choose the
result yourself: **if you choose "passed" against the suggestion,
Rentalars asks for the reason in the note.** A failed item becomes
"defective" as always; without a note the findings of the measurement are
its reason. An inspection type without the box takes no measured values.

**The limits**, as Rentalars holds them from DIN VDE 0701-0702 – the same
for every inspection, not configurable:

| Check | Limit | measured for protection class |
|---|---|---|
| Protective conductor resistance R<sub>PE</sub> | at most 0.3 Ω for a cord up to 5 m; 0.1 Ω more for every further 7.5 m **begun**, at most 1 Ω – so 0.4 Ω up to 12.5 m, 0.5 Ω up to 20 m (12.6 m already means 0.5 Ω), 0.9 Ω up to 50 m, 1 Ω beyond | I |
| Insulation resistance R<sub>ISO</sub> | at least 1 MΩ (I), 2 MΩ (II), 0.25 MΩ (III) | I, II, III |
| Protective conductor current I<sub>PE</sub> | at most 3.5 mA | I |
| Touch current I<sub>B</sub> | at most 0.5 mA | I (at conductive parts without protective conductor) and II |

**What must be measured.** For protection class I the protective
conductor resistance and a check of the insulation – the insulation
resistance or, as the standard allows instead, the protective conductor
current or the touch current; for protection class II the insulation
resistance or the touch current; for protection class III the visual
inspection is enough, and you enter the insulation resistance where you
could measure it. If any of this is missing, Rentalars suggests "failed";
"passed" then needs a reason in the note.

**Measured values and test report.** Under "Inspections so far" an
electrical inspection has, in the column **"Measured values"**, every
check with value, limit and verdict and the test device – folded, with "1
outside the limit" if a value failed – and the link **"Test report
(PDF)"**: one page with your company, the device (ID, serial number,
model, manufacturer, protection class, cord length), inspection type,
date, inspector and test device, the checks with value, limit and
verdict, the result – passed with "next inspection due by …" –, the
findings, the note and room for the signatures of the inspector and of
the responsible person, in the language of your documents. A protocol of
the test device you uploaded stays next to it in the column "Protocol".
Earlier inspections have no measured values.

**Through the interface** (section 16, "API tokens"): inspection types
name `is_electrical`; `POST /material-items/{id}/inspections` takes the
measured values – protection class and cord length from the item if left
out –, `POST /material-items/{id}/inspections/check` evaluates them
without storing anything, every inspection names its measured values,
`evaluation` and `report_url`, and `GET /inspections/{id}/report` returns
the test report.

**What is due:** **Material management → Inspections** lists all overdue
inspections and those due soon, the most urgent first, with storage
location and status. You can filter by inspection type, by state ("overdue
and due soon", "overdue", "due soon") and with "Due within … days" (30 by
default). A click on the ID leads to the item's inspections. At the top
right **"Inspection types"** (for everyone who may read the settings) leads to the management of the inspection types.

**Inspecting many items at once** (you need the right to change
material). Every row of the list has a tick box, the box in the header
chooses all on the page. As soon as an item is chosen, a bar with **"Inspect
chosen items"** appears below the list; it leads to the page "Inspect several
items":

- At the top is what holds for all: the **inspection** (only types that
  apply to all chosen items; the type you filtered the list by is already
  chosen), the **date** (today), **"Inspected by"** (you) and, for an
  electrical type, the **test device** – **once for all**, filled in with the
  one you entered last.
- Below, each item has a row with **result**, **note** and, for an
  electrical type, **"Visual inspection passed"** (the box in the table
  header ticks all), protection class, cord length, the measured values and
  the function test – as on the page of a single item. The result "by the
  values (electrical)" takes what the limits suggest; another choice holds,
  "passed" against the suggestion needs a reason in the note, as there.
- **"Record inspections"** saves one inspection per item. **All or
  nothing:** if one item breaks a rule of the single inspection, nothing is
  saved; the page keeps everything you entered and shows at the item what is
  missing. At most 1,000 items at once.

Through the interface: `POST /material-items/inspections/batch` (JSON) with
inspection type, date, inspector, test device and `items` – per item `item`
(the database ID), `result`, `note` and the measured values; errors name
the entry (`items[1].note`).

Once a day Rentalars reports newly due inspections to the warehouse – each
only once, collected in an "Inspections due" notification.

**And when packing?** The packing list points it out on a row if items of the
product have an overdue inspection. If you choose such an item for the
packing list or it goes out on issue, Rentalars warns you ("The inspection of
0742 is overdue."). It does not prevent anything – you have to decide.

### Audits and to-dos

An **audit** is a short check of an item: is the label still
there, the velcro on the cable, is it clean and complete? Unlike an
inspection it has no result per inspection type, no protocol and blocks
nothing – the piece is either **in order**, or you note what is to be done
as a **to-do**.

**Settings → Audits:**

- **Audit interval (months)** – 24 by default, i.e. two years; **0**
  switches audits off: then nothing becomes due, but audits and to-dos can
  still be noted.
- **Quick picks for to-dos** – one per line, at most 12; by default "Label
  missing", "Velcro missing", "Damaged", "Clean" and "Parts missing" (a
  German company gets them in German). They appear as buttons in the audit
  and on the page of an item.

The page is seen by those who may read the settings and changed by those
who may change them.

**When is an audit due?** One interval after the last audit – whatever it
found; the to-dos it noted are dealt with as to-dos, not by another audit.
An item **never** audited is due one interval after it was **created in
Rentalars** – not at once. A fresh installation or 3,000 items imported
today therefore do not all become due on one day but gradually, the oldest
first. **Retired, sold and lost** items and **bulk material** never become
due, but can still be audited.

**The audit mode:** **Material management → Audit** (for everyone who may
change material) – for a round through the warehouse, on the phone as on
the computer, also without JavaScript:

1. Under **"ID of the item"** type the ID or scan the label – `0427`,
   `427`, `#0427` or the address from the QR code –, Enter.
2. Rentalars shows the item with the last audit and when the next one is
   due, and below that its **master data** at a glance: ID,
   model, manufacturer, category, serial number, invoice date, "Bought
   from", with the right "See purchase prices" the purchase price,
   storage location, status, protection class, the category-specific
   values (the length, say) and the custom fields – confidential ones only
   with that right. Every detail is listed, an empty one too: as a red
   **"–"** (a screen reader says "not documented"), an empty required
   field with "required, missing". If something is missing, **"Edit
   item"** next to it opens the form; after saving – or with "Cancel" –
   you are back in the audit of the same item.
3. If everything is fine: **"In order"**. Faster is the field **"In order –
   next ID"** below it, where the cursor already is: type or scan the next
   ID, Enter – the item shown is recorded as in order, and the next one
   appears. Empty, Enter goes back to the field above.
4. If something is to be done: under **"Note to-dos"** tick the quick
   picks and/or type **"Another to-do"**, optionally a **"Note on the
   audit"**; open to-dos of the item that have been done in the meantime
   you tick under "Open to-dos – tick what is done". Then **"Save audit"**.

**"Audited in this round"** lists what you recorded in this round, with
result and time; **"New round"** starts a new one. The round belongs to
your login.

**To-dos on the item:** the page of an item has the box **"Audit and
to-dos"** with the last audit, the next one due, the **open to-dos** – each
with "done" to tick it off –, the field **"Note a to-do"** with the quick
pick buttons, the to-dos done lately (collapsed) and the **audits so far**.
"Record an audit" opens the audit mode with this item. You note a to-do at
any time, not only in an audit. An open to-do with the same text is not
noted twice; none is deleted, only done. Audits and to-dos are in the
item's history ("Audit: in order", "To-do noted: Label missing").

**Open points:** the tab **Material management → Open points** has three sub-tabs, each with the number of its
entries. The sum of these three numbers is also on the tab
"Open points" itself, on every tab of the material management – so you
see from anywhere whether and how much is open:

- **"Material without product"** – the items not yet assigned to a product
  and therefore not plannable (below, "Assigning material to a product").
- **"Material with to-do"** – one row per open to-do (without retired, sold
  and lost items), as a table like every list: search by to-do, name or
  ID, filter by to-do and category, group by to-do ("Label missing" on 20
  cables). Whoever may change material ticks rows and marks them done
  together with **"Mark chosen to-dos done"**.
- **"Audit due"** – the items whose audit is due, the oldest first, with
  the last audit, "Due since" and open to-dos; a click on the ID leads to
  the box "Audit and to-dos", the button **"Audit"** in the row opens the
  audit mode with this item, **"Start the audit"** at the top without one.

### Installed in – racks, cases, kits made of individual parts

If an item sits inside another – the radio receiver in the rack, the cable
in the case –, you install it directly on its page: under "Installed in /
contains", type the ID or name of the outer piece under **"Install in"**
and choose from the suggestions, choose the **"Kind of connection"**,
**"Install"**. The same is available under "Edit item" in the **"Installed
in (ID)"** field. The types of connection:

- **permanently installed**: screwed in, wired in, stays inside. The part
  only travels with its rack and is **not planned individually**. It does
  not count towards the plannable stock of its product.
  Exception: you tick **"can be rented on its own"** – for permanently
  installed parts that are taken out when needed after all.
- **loosely contained**: just lies inside. The part can still be planned
  individually. But if the case is planned, its loose contents count as
  **booked as well**.

An item's page shows both: what it sits in and what sits in it.

**From the other side: "Contains".** The same connection can also be
maintained on the outer piece. On the rack's page, under "Installed in /
contains", type the receiver's ID or name under **"Add an item"**, choose
the kind of connection and press **"Install here"**. Next to each content
it says how it comes out again: "take out" for loosely contained ones (see
"Taking out and putting back"), "remove" for permanently installed ones. It
is the same information as "Installed in" on the receiver – just entered
from the other side.

Circles are not possible: a rack cannot be installed in something that
itself sits inside it. And a piece that is already installed somewhere else
is not silently moved over via "Contains" – Rentalars says where it is; to
rebuild, you change "Installed in" on the piece itself.

> **Example.** The product T-050 "Radio receiver" has six items. Four of
> them are permanently installed in a radio rack. The product list shows
> the stock as "2 / 6 pcs.": six present, two plannable individually. Whoever
> books the radio rack gets the other four with it.

An item that still has something inside cannot be retired. First take out
the contents (empty "Installed in" on them).

Installation and removal appear with time and user in the history of
**both** items. If a part in a rack is defective or its inspection
overdue, the rack shows it at the top of its page – so it is noticed before
the rack goes out. If the rack goes out on an issue, its contents go with
it, and they come back with the return (section 10, "Choosing items").

### Built-in bulk material

Ten metres of cable and four connectors that always stay in a rack case,
a box of screws in the vehicle: you keep such **bulk
material** (above, "Bulk material") **as built into** an item. "Installed
in" does not do this – it is for single items; a row with a quantity has
its own box.

1. Open the page of the case, the rack or the vehicle. Under **"Built-in
   bulk material"** type the ID or the name of the bulk row under **"Build
   in"**, the **quantity** and, if you like, a note ("for the multicore").
2. **"Build in".** Rentalars refuses more than is free ("Only 8 of 0612 are
   free; 10 cannot be built in."), a row that is not fit for use and a
   target that is itself bulk material or retired.

What follows from it:

- The quantity built in **leaves the free stock** of the row – the stock of
  the product, the availability and the packing never count it twice.
  A row that is built in somewhere has the box **"Built into other items"**
  on its own page: "Free stock", "Built in" and "Together", and a table
  with "Built into", "Quantity", "Built in since" and "Built in by".
- The built-in material **goes out with the case**. Nothing has to be
  booked; on the case's packing list it stands under the case as "contains
  10 m × XLR cable" (section 10, "The packing list") and is not counted a
  second time.
- **Taking out:** next to each entry in the case's box is a quantity field
  and **"take out"**. Empty takes everything out; a number takes that many –
  the rest stays built in. The quantity is free stock again at once. On the
  bulk row's page, "take out" takes everything out of the case in that row.
- Building in and taking out are in the **history of both** items, with the
  quantity, the user and the time. There is no stock ledger beyond that:
  you see who moved what, but no running balance.
- An item with something built in cannot be **sold** from stock (below, "Selling
  used equipment from stock").

### Taking out, putting back and taking out for a project

**Taking out and putting back.** A loosely contained microphone is needed
elsewhere for a moment? On its page, under "Installed in", is the button
**"Take out of 0500"** – one click, and it is no longer in the case.
Rentalars remembers where it came from: afterwards it says **"Put back into
0500"** there, and one click puts it back in. On the case's page, "take
out" next to the content does the same. Permanently installed parts are not
taken out in passing; for them you change "Installed in" deliberately.

**Taking out for a project.** Sometimes a loose content is to stay in the
warehouse for *one* project only – the case goes to the customer, but
without the expensive microphone that is needed elsewhere at the same time.
For this there is the **"Taken out for projects"** section on the
microphone's page. It appears as soon as a running or upcoming project
takes the case along: choose the project ("Take out for project"), **"Take
out for this project"**.

- The microphone is **free** for others during this project.
- The project's **packing list** names what is missing: "0123 Radio microphone
  stays behind (taken out of 0500)" – on the case's row and at the top of
  the list.
- On issue the case goes out without the microphone.

**"travels with it again"** next to the project undoes the taking out.
Anyone who may pack (module "Packing and issue") may take things out.

### Assigning material to a product

On the **model**, "Product" field: applies to all its items. This is the
normal case.

On the **item**, "different product" field: only for the special case that
a single piece belongs to a different product from its siblings – such as
a modified device.

If the product belongs to a different main category from the material – a
stand from "Rigging/truss" on a product from "Sound" –, Rentalars points
this out when saving. This is not an error, but often a slipped mouse click.

The **"Material management → Open points → Material without product"**
list shows everything that is not
yet assigned to a product and therefore cannot be planned.

**Create as product.** If a model has no product yet, the **"Create as
product"** button appears on its page next to "Product". One click creates
a product with the model's name – a rental product, in a category for sale
a sale product –, with the next free article number and the category's
defaults, and assigns the model to it. Then the product's form opens:
enter the price, it is initially 0. Without the right to see prices, the
product's page opens, and someone with the right enters the price. The
button is available to anyone who may edit material and products. For
customer material it says "New product" there, because the product needs
its owner (section 5, "Customer material").

**From the product.** On a product's page under "Assigned material" you
create a model that belongs to it straight away with "New material model",
or take over an existing one with "Assign existing model" (section 5,
"Stock and availability of a product").

### Labels

Every item gets a label with its **ID** and a **code**:

- **QR code** – it contains the address of the item's page, such as
  `https://rentalars.eure-firma.example/m/0042`. Any phone's camera opens it;
  anyone who is logged in lands directly on the item's page and can report
  a defect or look up the inspections. Where the QR code of the labels for
  the label printer leads can be set (below, "Setting up labels").
- **Barcode** (Code 128) – it contains only the ID, for hand scanners; only
  on the sheets (below).

**Three labels for the label printer.** There are three labels
in your company's layout, made for Brother label printers:

| Label | Roll | What it shows |
|---|---|---|
| **"Small, 17 × 54 mm"** | DK-11204 | logo, name, QR code, phone number, web address, ID and, in small print, a text for finders |
| **"Large, 29 × 90 mm"** | DK-11201 | the same, larger – for devices, cases, racks |
| **"Cable, 29 mm roll"** | DK-22210, continuous roll | 18 mm blank at the start – the first wrap, covered by the following ones –, then a text that wraps around the cable and repeats across the tape, at most 14 mm apart; below it a flag with logo, the shorter name for cables, web address, phone number, ID and, under them, the QR code. 60 to 200 mm long, 90 mm by default – a longer label repeats the text more often |

On **customer material** "Owned by …" with the customer's name appears
instead of your name (section 5, "Customer material").

**Easy to read**. The three labels are printed in the font
**Liberation Sans** – metrically the same as Arial, the font of your
P-touch templates, and shipped with Rentalars –, in the font sizes of the
templates and in pure black; a text is made smaller only if it does not
fit its box. The logo prints in black and white at the printer's
resolution. Everything lies inside the area a Brother QL printer can
print, with a little margin at the ends – so the printer does not cut
anything off. The **QR code** sits at the place of the template and is at
least as large as there – about 8.5 mm on the small label, about 16.8 mm on
the large one, about 8.2 mm on the cable label –, but grows into the free
space beside it (whole printer dots, so the code stays sharp).

**Like the originals**. On the small and the large label the
title stands in the template's size across the full width, below it the logo
and text beside the QR code; the "text for finders" stands in its field of
the template. The cable flag has the QR code at the bottom left, the logo
above it and the texts beside; the text around the cable repeats five times
instead of three at 90 mm. An ID with eight digits is set smaller instead of
being clipped. **The order in the title** ("Max Muster - BSP" or "XYZ -
Max Muster") is printed as you type it under Settings → Labels at "Name on
labels" – likewise the spelling of the web address (at "Text around the
cable"). If a label differs from your template, change these settings first.

**How it works:**

- **One label:** **"Label"** at the top of the item's page
  opens a small window with the three labels – the one suggested under
  Settings → Labels first – and below them "Sheets and roll". A click
  opens the print page of exactly this label in a new tab, with the print
  dialog (below). "More settings" leads to the "Labels" page. Retired,
  sold and lost items get no label; the window says so.
- **All items of a model:** **"Labels"** at the top of the model's page
 leads to the "Labels" page with all items of the model
  that are still there.
- **A selection:** in "Material management → Items" tick the items and
  press **"Labels"** in the bar at the bottom (see "Changing many items at
  once"). After "Enter a purchase", "Print labels" leads there with the new
  items (above, "Entering a purchase").
- **A range:** these buttons lead to the "Labels" page. There the selection
  can be changed under **"IDs"** – separated by commas or spaces, ranges as
  `0100-0120` – or a whole range can be given with "or all from ID" … "to
  ID".

On the "Labels" page you choose one of the three labels under **"Label"**
– the one
suggested under Settings → Labels is preselected – and press **"Print"**.
A new tab shows the labels, one per page in its exact size, and opens the
browser's print dialog by itself. There choose

- the **label printer**,
- the **paper in the size of the label**, such as 17 × 54 mm,
- the scale **100 % (actual size)**, not "fit to page",
- **no margins**.

The bar above the labels says so once more, with the matching Brother
roll; its "Print" button opens the dialog again. Up to 240 labels at once
can be printed straight from the browser. **"Make the PDF"** makes the
same labels as a file, also for more. "Show the choice" lists the chosen
items; the "Labels" page stays open in case you need more.

**The sheets of before** can still be chosen under "Label":

| Sheet | For |
|---|---|
| A4, 24 labels 70 × 37 mm (3 × 8) | devices, cases, racks |
| A4, 65 labels 38.1 × 21.2 mm (5 × 13) | cables and small parts |
| Label printer, 62 × 29 mm, one per label | roll printers |

They carry ID and short name, and for them you choose the **code** – "QR
code (opens the item's page)" or "Barcode (Code 128, the ID)". On the
larger ones your company name also appears under a QR code – for customer
material "Owned by …", for the barcode under the name. If a sheet has
already been started, **"Leave free at the start"** says how many fields
are skipped. You print sheets via "Make the PDF", at actual size
("100 %"), otherwise the labels will not fit on the sheet.

More than 240 labels at once are made as a PDF **in the background**: you
can carry on working and are told as soon as the PDF is ready; it is then
under My account → "Tasks in the background". At most 5,000 labels can be
made at once.

**Setting up labels.** What the three labels show, an administrator sets
under **Settings → Labels** – also via **"Set up labels"** on the
"Labels" page:

- **"Logo for labels"** – PNG or JPEG, ideally square; black and white
  prints best on a label printer. Empty: the logo from the company data.
- **"Name on labels"** next to the logo and the shorter **"Name on cable
  labels"**.
- **"Phone number"** and **"Words before the phone number"** ("Telefonnummer:"
  by default), and **"Words before the ID"** ("Equipment-ID:" by default).
- **"Web address printed"** – as it is to appear on the label, such as
  `EXAMPLE.DE`.
- **"Text around the cable"** – it is printed exactly as you type it, in
  upper and lower case. Left empty, the printed web address appears there,
  as it stands in the field above or in the company data (often in lower
  case). If you want it in capitals around the cable, type it here like
  that, such as `EQUIP.EXAMPLE.DE`.
- The **"Text for finders"**, such as where to report a found device.
- **"QR code leads to"** – a web address with `{id}` where the ID belongs,
  such as `https://equip.example.de/id/{id}`; empty, it leads to the item's
  page in Rentalars.
- **"Label suggested"** and the **"Length of the cable label (mm)"**.

Empty fields take the details from Settings → Company data and settings.
Beside them a **preview** shows the three labels using the item 0427, as
saved. A dashed line in it shows what the label printer can
print – it is not printed –, and below the cable label it says how long
its blank start is. If the cable label is too short for the 18 mm, the
blank start is shortened, and the preview says so.

### Scanning labels and codes

You need not type an ID where you can read the label: with the
phone's camera, with a hand scanner or by typing. There are three places for
it, all optional:

- the field **"Item ID"** in the head of every tab of the material
  management (above, "Opening an item by its ID");
- the packing list, when packing and when taking back (section 10,
  "Packing with a scan");
- the planning, with **"Scan items"**, which plans exactly the item scanned
  as a wish (section 7, "A particular model or item").

**What a code can be.** Rentalars knows the content of the label's QR code
(the address `…/m/0042`, or the one you set under Settings → Labels as "QR
code leads to"), the plain ID that the bar code of the sheets holds, a serial
number, the GTIN (EAN) of a product – 8, 12, 13 or 14 digits –, a storage
spot such as `01-A-1` and the name of a storage location. In the item field
an item opens its page, a product its page, a storage spot or location the
list of the items that lie there. A code that Rentalars does not know – or
that leads to something you may not read – is answered with "Nothing is known
under …"; a scan does not reveal what exists.

**The "Scan" button** opens the window "Scan a code":

- With the **camera**: hold the code in front of it. This works only on a
  page served over **HTTPS** (a test server on the same computer counts) and
  in a browser that reads codes from the camera picture – that is Chrome, Edge
  and Chrome on Android; in **Firefox and Safari** type the code or use a hand
  scanner. The browser asks for permission to use the camera. **No picture leaves the browser**:
  it decodes the code and sends only its text. A "Torch" button appears where the camera has
  a light.
- With a **hand scanner** or by typing: the window always has the field
  **"Type or scan the code"**. A USB or Bluetooth scanner that types like a
  keyboard needs nothing else – it types the code and the final Enter.
  Where the camera cannot be used, the window says why ("The camera needs a
  secure connection (HTTPS). Type the code or use a hand scanner.") and the
  field is still there.

The same reading is available to other programs through the interface
(section 16, "API tokens"). **Not tried with real hardware yet:** the camera
and the browsers' code reader, real label printouts and USB scanners were
tested only in simulation; try your own devices and labels first (section
17).

### Changing many items at once

Twenty new cables go onto shelf B, a whole case goes into repair: in
**Material management → Items** every row has a box at the front (this
needs the right to change material). The box in the table header chooses
all on this page – set the page length to 200 (or up to 1,000 under "Own
number") or filter first if there are more.

As soon as an item is chosen, a bar appears below the list – while you
scroll it stays at the bottom edge, like the bar of the chosen lines in the
planning. It shows how many are chosen, and next to that:

- **Status** – with **reason**; for "defective" it is required,
- **Storage location** – or "no storage location",
- **Storage spot** – empty leaves the spots as they are;
  another storage location without a new spot removes the old one,
- **Product** – or "as the model".

Whatever stays on "– leave as it is –" stays as it is. **"Change chosen
items"** changes all of them at once, at most 1,000.

**All or none:** if a single item breaks a rule – such as a defective one
that is to become "available" –, Rentalars changes nothing and names the
item. Every change appears in the history of the individual item. Notes
that do not hold anything up appear afterwards: that installed items stay
where their device is, or that a product belongs to a different main
category.

**"Labels"** in the same bar leads to the "Labels" page with the chosen
items (above). **"Clear choice"** removes all ticks; without ticks the bar
disappears again.

### Timeline

When is this device free? The **"Timeline"** tab on every item and every
model (likewise on products and people) shows weeks side by side, day by
day:

- on the **item** its deployments, projects that want exactly this item,
  periods with its device or taken out of it, blocked periods and due
  inspections; below that, how many pieces of its product are free on each
  day, and the projects that need the product;
- on the **model** the free pieces of its product and one row per item (the
  first 40).

The numbers in the "free" row are the day's free pieces; the small number
next to them what options would take in addition. Bars show firm
reservations, options, what is out of the house and what is blocked – the
legend is below. Projects you may not open appear with their number only.
The tab on items, models and products is there only with the
special right **"See availability of material"** – the role Crew does not
have it (section 16, "Roles and rights").

At the top you choose the period: **"‹ earlier"**, **"this week"**,
**"later ›"**, a date under **"From"** and the number of **"Weeks"** (one
to twelve).

### Evaluations: choosing a year

The year selections (profitability, material evaluations) offer
five years back and **three years ahead**; the current year is preselected,
and a year in the address stays as it is.

### Calendar link

When is the device out – in your own calendar, without opening Rentalars?
Every product, material model and item can get a **calendar
link**: a secret address in the iCalendar format (.ics) that your calendar
program subscribes to. By default none has one.

The box **"Calendar link"** is on the page of the item (tab "Item", at the
bottom), of the model (tab "Model", below its items) and of the product
(tab "Product", above the history). It says what the calendar shows and
has:

- **"Create calendar link"** – then the address is under **"Address for
  calendar programs"** with **"Copy"**, and below it when and by whom it
  was created;
- **"Create a new link"** – replaces the address by a new one; the old
  one stops working at once;
- **"Deactivate link"** – switches the address off without a new one.

The last two ask first. Each of these changes is in the history of the
product, model or item ("Calendar link (iCalendar) created"), the address
itself never – nor in the change log.

**Who may.** The box is shown to whoever may read the module – "Products"
for a product, "Material" for a model or an item –, has the special right
"See availability of material" and may read all projects, not only
assigned ones: the calendar names projects, and without a login. Creating,
replacing and deactivating needs write access to the module as well – and
only those who may do that see the **address**: it works without a login,
and only someone who may change the link can end it. Whoever may only read
sees that a link is active, since when and by whom, and what the calendar
shows. The role Crew does not see the box.

**What the calendar shows** – what the timeline shows (above), as
appointments from 90 days back to two years ahead:

- for a **product** every booking in a project, also in a kit or case:
  "3× 2027-0042 City festival", in the description project, status and
  quantity, the period with the buffers before and after; an option or
  optional line as a tentative appointment ("– Option"), a sale on the day
  of the sale; and the blocked periods of its items;
- for a **model** the same for the product of its items (if single items
  have a different product, for each of these products, with its name);
- for an **item** when it is out with a project ("Out: …") or chosen for
  its packing list, when a project wishes for exactly this item, when it
  travels with its device or is taken out of it, its blocked periods and
  due inspections. Bookings of its product that name no item are in the
  calendar of the product.

Each appointment links to its project; only someone who logs in and may
see it can open it. **Not** in the calendar are prices, customers, contact
data and places. When a booking changes, the calendar program changes its
appointment instead of adding a second one. The texts are in the language
of the installation.

**Subscribing.** Copy the address and add it in your calendar program as a
subscribed calendar – "From URL" or "Subscribe to calendar", depending on
the program. The program then fetches the appointments itself and keeps
them up to date (Rentalars asks it to check every 30 minutes). It has to reach
Rentalars for that; Google Calendar, for instance, fetches the address from
its own servers, so only if Rentalars can be reached from the internet.

**Treat the address like a password.** It works without a login: whoever
knows it sees these appointments. Pass it on only to those you want to
show them; if it got into the wrong hands, use "Create a new link".

**When the material goes.** If an item is retired, sold or marked lost,
or a product is deactivated, its calendar link is deactivated for good (in
the history: "Calendar link deactivated: the record is no longer in use");
if it comes back, it needs a new link. A deleted record takes its link
along. A product without stock of its own – a kit or a service, say – has
no box. The interface does the same: `GET`, `POST` and `DELETE` on
`/products/{id}/calendar-link`, `/material-models/{id}/calendar-link` and
`/material-items/{id}/calendar-link` (section 16, "API tokens"); `GET`
names the address (`url`) only to whoever may change the link.

### History

Every item has a history: when it was created, every status change, every
change to its data – also to the values of its custom fields –,
every installation and removal, every defect report, every
audit and every to-do noted and done, and which projects it was out with –
each with time and user. So that the
list stays readable, the individual changed fields are collapsed: "3
changes" expands them with the old and new value.

### What an item earns

Has the device paid for itself? An item's page shows the box
**"Earnings"** – for everyone who may see the reports (section 8): it adds
up the projects of all customers. It loads shortly
after the page, because Rentalars goes through all projects for it:

- **"Earned with this item"** – in total, and in how many projects;
- **"of it assigned"** – from the projects it was chosen for when packing:
  per project one piece's share of what the lines of its product brought
  in;
- **"of it estimated"** – its share of the pieces that went out without an
  item chosen. Which of the twenty cables went along, usually nobody
  knows; Rentalars shares such pieces out evenly over the items the
  product had then.
- **"Share of the purchase price"** – what was earned against the
  "Purchase price (net)", as a percentage and a bar: yellow from 50 %,
  green from 100 %. These rows show only to those who may see purchase
  prices. An item **bought as a set** (above, "Creating new material") is
  compared together with its set: "The set earned" against the "Purchase
  price of the set".

What counts are the lines after their discounts, in projects whose
material went out ("Out", "Returned", "Closed"); a kit's line is
shared out to its components by their prices. Optional and alternative
lines and customer material earn nothing. The same calculation per product
is under Reports → "Material" (section 8, "Reports").

**What a model earns.** A model's page has the box
**"Earnings"** as well – for the same people and calculated the same way,
but added up over all its items: **"Earned with the items of this model"**
and in how many projects, "of it assigned" and "of it estimated", and with
the right for purchase prices also **"Purchase prices together (net)"** and
**"Share of the purchase prices"**. If the model has several items, a table
below lists per item what it earned, in how many projects and – with the
right – its purchase price and share; this table is folded:
**"Earnings of each item (12 items)"** opens it, without JavaScript too,
and the sums above always stay in sight. An item bought in a set counts with
its share of the set's price.

### Fixed assets, depreciation and book value

What is the equipment still worth in your books? Rentalars can
tell, item by item – for everyone who may see **purchase prices**. This is a
**simplified standard setting and no tax advice**: your tax adviser decides
what is booked. Rentalars checks the **low-value limit** (net per piece, in the
settings): if a piece costs more, choose "fixed asset" – in the form, when entering a purchase and for bulk
material (cost per piece).

**Kinds.** Every item can be recorded as

- **merchandise** – it stays at its cost until it is sold, no depreciation;
- **low-value asset (GWG)** – written off completely in the year of purchase;
- **fixed asset** – written off over its useful life.

Items booked in from an incoming invoice (section 11) get their kind there,
with the ancillary costs spread over them. An **older item** you record by
hand: on its page, in the box **"Asset accounting"**, open **"Record as
asset"** (later "Change the asset data"). There you choose the **kind of
asset**, for a fixed asset the **useful life (months)** – empty means the
standard of the settings –, the **ancillary acquisition cost (net)** and the
**acquisition cost (net)**; empty, the cost is the item's purchase price. **"Save asset data"**. This needs
the right to edit material too. For bulk material the amounts are those of
the whole row.

**The rules** – the same for everyone, not configurable:

- A fixed asset is written off **in a straight line by month**; the month of
  purchase counts in full. A year as the only date known counts as January
  (above, "Purchase date not known exactly").
- The amount written off is rounded to cents and the last month balances, so
  that the instalments add up exactly to the cost.
- A low-value asset is written off on **31 December of the year of
  purchase**; before that day, in that year too, its book value is the full
  cost. The limit is **800 € net by default** (inclusive) and is set under
  Settings → Incoming invoices (section 16); the standard useful life is 60
  months.
- With the setting "Keep a memory value of 1 €" a fully written-off fixed asset
  stays in the books with 1 € until it is sold or retired. It is off by
  default.
- A purchase date **in the future** means "not acquired yet": the item is not
  in the sums. An item without cost, date or useful life has **no book
  value**; the register lists these separately.
- **Not covered:** degressive depreciation, special depreciation, the
  half-year rule, the collective item for low-value assets and later
  additions to the cost. There is no DATEV export of these figures.

**The box "Asset accounting"** on the item's page shows the kind (with the
useful life), the date of purchase, the acquisition cost, "Depreciation until
today", the "Book value on today's date", the state ("depreciating – 23
months left", "fully depreciated", "not acquired yet", "no useful life" …)
and the table **"Depreciation per year"** with the months, the amount, the
sum so far and the book value on 31 December. The box "Purchase" above it
shows the acquisition cost with the share of the ancillary costs and a link
to the position of the incoming invoice.

**Accounting → Asset register** (right "See purchase prices" and read access
to the material) lists the items recorded as fixed or low-value assets –
merchandise, items not recorded and "Everything" you choose under "Kind of
asset": ID, model, kind, date of purchase, useful life,
acquisition cost, depreciation so far, depreciation in the year, book value,
state and more via "Columns". It is a list like any other (section 2,
"Lists"): sort, group, CSV. You filter by search (ID, model, serial number,
note), kind, storage location and model, choose the **balance-sheet year (31
December)** or **"Or on this day"** for the values of another date, and
**"Also items that left the stock"**. Below the table are the **sums per
kind** – count, acquisition cost, depreciation so far, depreciation in the
year, book value – over all items of the filter. Items without a book value
and those bought only after the day are named below the sums and are not
counted.

### Selling used equipment from stock

A device you no longer need goes to a customer or a colleague. You sell it **from stock** – with the book value on the day of the sale and
the gain or loss. For everyone who may see purchase prices and edit
material.

1. Open the item and click **"Sell from stock"** in the box "Asset
   accounting".
2. Enter the **day of the sale** (not in the future, not before the
   purchase), the **buyer** – a **customer** of your master data or a **name**
   you type –, the **price (net)**, the **tax rate** and a note. For bulk
   material there is also the **quantity**: a part of the row is sold.
3. **"Show the preview"** shows price, tax, gross, the acquisition cost, the
   depreciation until the day, the **book value on that day** and the
   **gain or loss** ("price (net) minus book value"). An item that was not
   recorded as an asset with cost and date goes out with a book value of
   0 €, so the whole price is a gain – the preview says so. A low-value asset
   sold before 31 December leaves the books at its full cost.
4. **"Sell"**, after you confirm. The item gets the status **"sold"** (the
   usual way an item leaves the stock, above, "The condition of an
   item"); the history notes the sale without amounts.

**What stops a sale** is shown instead of the button: the item is chosen or
packed for a project or out with one, it is installed in another item, has
other items or bulk material installed in it, or has already left the stock.
What only gives pause – a project's planning wishes for exactly this item, a
blocked period that has not ended – needs the box **"Sell it anyway"**.

**Accounting → Sales from stock** lists the sales: day, item, buyer, quantity,
price net, tax, gross, kind, acquisition cost, book value at the sale, gain
or loss. Filter by search (buyer, item, model, note), year and period, and
**"Also reversed sales"**; below the table is **"Gain and loss per year"**.
Click a sale for its page.

- **"Create an invoice for it"** makes a draft of an invoice without a
  project for the buyer (section 11, "Outgoing documents without a
  project"), with one line "Used equipment: …". This works only if the buyer is a
  customer. The draft is **linked** to the sale: a second click
  gives the same draft as long as it is open; once the invoice is made, its number
  stands at the sale, and Rentalars refuses a second invoice for the same sale
  until you have cancelled the first. A sale with a valid invoice cannot be
  reversed – cancel the invoice first (Accounting → Outgoing documents).
- **"Reverse the sale"** (with a reason) as long as the item is still "sold":
  it gets its former status back – for bulk material the pieces and their
  cost go back into the row. The sale stays in the list as "reversed" and
  counts for nothing. If the status was changed meanwhile, set it by hand.
- Anonymising a customer (section 6) removes the name from the sales, the
  history of the item and the log.

There is no DATEV export for the sales, and no automatic booking in an
accounting program.

### Fleet

You keep your vehicles (motor vehicles) and trailers in the
material management, in the tab **"Fleet"**. A vehicle is an **item** –
with ID, status, inspections, files, defect reports, label and history like
any other – of a model whose product has the product kind **"vehicle"**
(section 5, "Product kinds"). The product carries the rates it is billed
by; the model says what kind of vehicle it is. Vehicles are not planned as
material but in the block "Logistics" of a project (section 7,
"Logistics"); they do not count towards the availability of material and
are not packed.

**Creating a vehicle:**

1. Create a **product** of the kind "vehicle" – easiest in the category
   FZ "Fleet", which presets the kind –, as a motor vehicle or a
   trailer, with its rates (section 5, "Product kinds").
2. Create a **material model** for this product and one **item** per
   vehicle (above, "Creating new material").
3. On the page of each item, in the box **"Vehicle data"**, click **"Edit
   vehicle data"**: **"Licence plate"** (each only once), for a motor
   vehicle **"Seats min."** and **"Seats max."** – required; different for
   removable seats, both the same for a fixed number –, **"Driving licence
   class"** (for a trailer the class of the combination, e.g. BE), for a
   motor vehicle **"Towing capacity (kg)"** (0: may not tow) and for both
   **"Permissible total weight (kg)"**. Whoever may edit material may do
   this.

Below the vehicle data are the **"Bookings"** of the vehicle now and in the
coming twelve months, with "now" and "overlaps another booking". Projects
you may not open show only their number.

**The tab "Fleet"** lists the vehicles and trailers with licence plate,
type (motor vehicle or trailer), model, product, seats ("seats missing" if
they are not entered for a motor vehicle), driving licence class, status,
next inspection (overdue in red) and the current or next booking
("overlapping bookings"). Towing capacity, total weight, serial number and
invoice date you add under "Columns". You can filter by licence plate,
model or serial number, by type and by status ("All in use" leaves out
what is retired).

**"Utilization of the fleet"** at the top of the page shows each vehicle's
bookings over all projects as a timeline, in the colours of the personnel
plan (firm, option, inquiry), blocked periods as bars of their own. If a
vehicle is booked twice at the same time – in one project or in several –,
the bookings are filled red and "!" stands in front of the name. It works
like the material utilisation (section 15).

**Deadlines.** Main inspection (HU), inspection under DGUV/UVV or service
you create as inspection types for the category FZ or the models (above,
"Inspections"). What is overdue or due before a booking ends is also named
in the project's logistics.

**Vehicles kept as material so far.** If you have planned the van as a
rental product until now, the page of its model shows **"Take into the
fleet"** (for everyone who may edit material and products) – only if the model's category or a parent category presets the product
kind **"vehicle"**, like FZ "Fuhrpark" (section 16, "Master data"). So a
cable or a spotlight does not have the button; if the van is still in
another category, give its model such a category first. The dialog and
the interface refuse other models ("Only models of a vehicle category
(product kind “vehicle”) are taken into the fleet."). The dialog asks for
the vehicle type, with the price right for the rates, with the
right for purchase prices for the internal costs. Rentalars creates a new
vehicle product – next free number of the category, name, unit, tax rate
and maximum discount from the previous product; a trailer's day price
starts as its price – and assigns the model to it. The previous product
and all lines stay as they are; no price and no sum changes. But the
previous product no longer has the items: open projects that still plan it
as material are named on the page afterwards ("These open projects still
plan … as material: …"). Book the vehicles there under "Logistics" and
remove the material lines – until then they show a shortage. Customer
material, bulk material and material of other product kinds cannot be
taken over.

### Taking over the Excel list

"Material management → Import" guides you through three steps: choose the
file, assign the columns, trial run – and only when the trial run is free
of errors, import. Trial run and import run in the background; the page
shows the progress, and you can carry on working in the meantime. There is
no limit on the number of rows in the browser. How importing works
in general is described in section 16, "Import and export"; everything else
about the columns of the material list and about importing repeatedly is
in the guide [Taking over the material list](operations/import.md).

The dry run shows **every row of the file** with its outcome –
new, changed (each field with "previously" and "new"), unchanged or error
–, for material also changes to the model ("Description (material
model)") and notes such as "new material model …" or "new supplier …"
(section 16, "Import and export"). If cells of the file have errors, only
the rows with errors are listed at first; the next dry run checks the
others. Whoever may not see purchase prices sees their values as "not
visible" – the purchase prices of the file are taken over all the same,
and the report says so.

The following also applies:

- **Net or gross.** Rentalars keeps purchase prices net. In the step
  "Assign the columns" the import therefore asks **"The purchase prices of
  the file are"** "net – stored as they are" or "gross – the tax is taken
  out", and for gross prices **"Gross prices include"** – the tax rate,
  the default tax rate preselected. A gross price is divided by 1 plus the
  rate and stored net: €119.00 with 19 % becomes €100.00. The report says
  so ("read as gross with 19 % tax and stored net").
- **IDs with "#".** A cell such as `#0802` is read by the import as the ID
  `0802` – in the ID column, in "Einsatz/Verbindung" and in the purchase
  price column.
- **Several IDs or text in "Einsatz/Verbindung".** An item is installed in
  at most one other. If the cell holds exactly one ID, that is the
  connection. If it holds several (`#0123, #1234`) or text (`Rack`), the
  import makes **no** connection and does not report an error either: the
  text is afterwards in the note of the item ("Einsatz/Verbindung: …"), and
  the preview and the report name the row as a note. You make the
  connection on the item.
- **Bought as a set.** If the purchase price cell says `#0851`, that means:
  bought as a set, the price is noted at 0851 (above, "Creating new
  material"). The item gets no price of its own and is linked to 0851.
  0851 has to be in the file or already in Rentalars; if 0851 itself names
  another item, the one at the end of that chain counts, and a chain that
  runs in a circle is an error. If the item with the price has no purchase
  price, the dry run gives a note. The report lists the sets bought
  together, the item with the price first.

Also:

- **Status "import error".** An entry Rentalars cannot read or accept – a
  purchase price like "neun", an invoice date like `32.13.2019`, a protection
  class that is none, a status that does not exist, a quantity that is not a
  whole number, an installed-in ID that does not exist, a reference to a set
  that points nowhere – **does not stop the import**. The item is taken over
  without that entry (an existing one keeps its old value), gets the status
  **"import error"** ("Fehler Import" in German), and its note names each entry
  in a line: the heading of the column in the file and the content of the cell
  ("Kaufpreis: neun"). An item with this status is **not fit for rental** until
  you fill in the fields by hand and choose another status; you cannot set this
  status yourself, only the import does. The report and the dry run count the
  items ("3 items get the status "import error""), and every row is in the list
  with its note. If you read the same file again later without the problem, the
  item is free again: it takes the status from the file, else "available"; the
  lines in the note stay only once. **Exception:** an item that is not fit for rental anyway (sold, retired, lost, blocked, defective, in repair) keeps its status and the reason for it; the note names the entries all the same, and a later clean import does not make it available again. **Errors remain** errors where there is no
  substitute: a missing or doubled ID, a missing article name or category, an
  item outside the file that forbids a set inside a set – Rentalars then writes
  nothing (all or nothing).
- **Quantity of individual items.** If you set "Menge (bulk material)" to
  "– do not import –" and an item still has a quantity from earlier times (it
  was bulk material), the message "individual items always have the quantity 1"
  is gone: the quantity is set to 1, the old value is in the note, and the report
  names it as a hint.

When importing on the server with `rentalars import_material`, `--gross`
and `--tax-rate 19` say the same (guide "Taking over the material list").

Also:

- **Custom fields.** A column headed with the name of a custom field
  (above, "Custom fields") fills that field – without mapping; the names
  are listed in the import under "Which columns are recognised?". Each
  value is checked against the fieldset of the model as in the form; a
  field the fieldset does not have, a value that does not fit or a unique
  value another item already has is an error of that row. An empty cell
  empties the value. The import does not demand required fields – as when
  creating several items at once. It skips the column of a confidential
  field with a note if you may not see purchase prices.
- **Storage location as a path.** `Halle 1 > Regal A` means shelf A in hall
  1 – important when two shelves have the same name.
- **There and back.** What the export in the import format writes, the
  import reads back unchanged; an apostrophe the export puts in front of
  text such as "=Summe" or "- defekt" is taken away again by the import
  (section 16, "Import and export").

The **protection class** (above, "Protection class"): the
column **"Schutzklasse"** (also "Schutzkl.", "SK" or "Protection class")
names the class of the item as `I`, `II` or `III`; the import also takes
`1`, `2`, `3` and spellings such as "SK II" or "Schutzklasse 2", anything
else is an error of the row ("“IV” is not a protection class. Write I, II
or III."). A model **without** a protection class gets the class all its
rows of the file name – only if they agree and no item has a class of its
own; otherwise each item whose row differs from its model gets a class of
its own. The same class as the model, or an empty cell, means "as the
model" and takes an item's own class away. The import never changes the
protection class of a model that has one – do that on its page. The
export in the import format writes the class that applies to the item.

---

## 5. Products

A product is what appears in projects. It has an article number, a name, a
unit, a price and a tax rate.

### Product kinds

| Type | For | Stock |
|---|---|---|
| **Rental product** | comes back after the project | from the assigned material |
| **Sale or consumable** | stays with the customer or is used up | from the assigned material; leaves it for good on issue |
| **Service** | the price of a job function of the personnel – sound technician, stagehand, project planning; is only planned under personnel | none – is not checked for availability |
| **Incidental costs** | transport, travel costs, fees – planned like material, flat rate by default | none; does not appear on the packing list |
| **Kit** | a package made of other products | results from its components |
| **Surcharge** | fixed amount or percentage | none |
| **Subrental** | material from a supplier | none |
| **Vehicle** | a motor vehicle or trailer of the fleet, billed per kilometre or per day; is only planned under logistics | its vehicles are the items of the assigned material; they do not count towards the availability of material |

**Services belong to job functions.** Every service product belongs to
exactly one job function of the personnel and every job function to exactly
one service product, both with the same name. If you create a product of
the "service" type, the job function for it is created on saving; if you
create a job function, its product is created (section 12, "Job
functions"). Rentalars does not accept a name that a job function already
has for a new service. If you rename one, the other follows, as long as
both had the same name. A job function's product keeps its type and cannot
be deleted on its own; you delete the job function, and the product goes
with it. Services are only planned via a project's personnel, not as
material and not in kits (section 7, "Adding a line").

**Incidental costs** are whatever is neither material nor personnel: the
transport with the Sprinter van, travel costs, fees. They have no stock, do
not appear on the packing list, are charged as a flat rate by default and are
added in the project like material. The category N "Incidental costs" is
supplied for this. Your **own vehicles** you
plan with the product kind "vehicle"
under logistics (below).

**Vehicles** are the products of the fleet (section 4,
"Fleet"). If you choose the kind **"vehicle"** – preset in the category FZ
"Fleet" –, the form asks for:

- **"Vehicle type"** – motor vehicle or trailer;
- for a motor vehicle **"Price per kilometre (net)"** (required) and
  **"Trailer surcharge per kilometre (net)"** – added on every trip on
  which the motor vehicle pulls a trailer;
- for a trailer **"Trailer billed"** "per day" or "per kilometre" – how a
  new booking starts, switchable in the project – and with it the **"Price
  (net)"** per day (with the rental scale, like material) or the **"Price
  per kilometre (net)"**;
- with the right for purchase prices **"Internal cost per kilometre"** –
  fuel, wear, insurance – and for a trailer billed per day **"Internal cost
  per day"**.

Only those who may see prices see and change the rates, only those who may
see purchase prices the costs. A vehicle has no billing mode. The
product's page shows the vehicle type, rates and costs and under
**"Vehicles"** its models and items. A vehicle booked in projects stays a
vehicle of its type. It cannot be part of a kit.

### Creating a product

**Material management → Products → New product.** First choose the
**product kind**, then the **category**: the categories that preset this
kind appear at the top of the list ("Categories for "rental product""), the
others below them ("Other categories"). The category suggests the next free
article number and fills in sensible defaults (unit, billing mode); the
chosen kind is kept. If you choose the kind or category for a new product,
the form reloads – so enter the name and price afterwards.

**The article number** begins with the code of the main category, followed
by a number: `K-005`, `T-100`. You can change the suggested number as long
as it matches the code and is still free. If a product is already used in
projects, changing its article number needs a right of its own. If you
choose another category in the form of an **existing** product – say
after "Create as product" (section 4), when the model landed in the wrong
main category –, Rentalars suggests the next free article number of the
new category at once; everything else you entered stays.

**One product, one price.** **Price (net)** is the price **per day** for
rental products. Every product has exactly one price: a sale
product its **sale price**, every other product its **price** – the form
shows the field "Sale price" only for the kind "Sale", and the product
list shows it in one column "Price". So what you sell is a sale product;
if a rental article is to be sold as well, you create a sale product of
its own for it. Lines that already sell a rental product keep
their price (section 7, "Editing a line"). Which fields are required for
the chosen product kind – the price for all kinds except sale and service,
the sale price for sale products – is shown by their asterisk (section 2,
"Required fields").

**Duplicating**. On a product's page, **"Duplicate"** opens
the form of a new product, filled in with the original's details and the
next free article number of its category – prices only with the right
"See prices and calculation", internal costs only with the right for
purchase prices. Not taken over are the GTIN, the assigned material and
"deactivated". Nothing is saved before **"Save product"**; a kit then
brings its components along – the form names them under "Components of
the kit". The button is there for whoever may edit products.

A **service** also has, below the price, **"Limit in hours per day"** and
**"price per hour from the limit (net)"** – for a higher hourly price from
a certain number of hours per day (section 12, "What personnel costs and
earns") – and the **"Surcharges for night, Sunday and holidays"** tick
box (ticked): if you untick it, crew lines of this service get no
surcharges, neither in the price nor in the costs – for example for a night
watch whose price already includes the night. The product's page shows it
under "Surcharges". Other product kinds do not have this tick box: only
crew lines get these surcharges. By default a service is charged by the
hour.

**Maximum discount.** As on a job function, you also set a **"maximum
discount in percent"** on a product: empty means no limit, 0 means not
discountable. It limits every line of this product – its own discount, the
customer's default discount and its share of the group's discount or flat
price. If both product and job function apply, the stricter limit counts.
The product page shows the value under "Maximum discount" ("5 %", "not
discountable" or "no limit"); in the product list you show the "Maximum
discount" column via "Columns" – it goes into the export and is read back
in on import. The field and column can only be seen and changed by those
who may see prices.

Creating or changing many products at once – new prices for the whole
catalogue, say – works with the import of products under Settings → Import
and export or Material management → Import, tab "Products": download the
list as CSV, change it in the spreadsheet, read it back in (section 16,
"Import and export"). The button "Import" above the product list is gone
; "Enter a purchase" is there now (section 4).

### Billing modes

| Billing mode | How the amount comes about |
|---|---|
| daily rental per piece | quantity × daily price × factor for the rental days |
| daily rental per kit | as above; the quantity is the number of kits |
| flat | quantity × price – regardless of duration |
| by the hour | quantity × hours × price |
| by effort | quantity × price; the quantity is estimated at first and later replaced by the actual effort |

### Rental scales

Whoever rents for longer pays less per day. The scale turns the number of
rental days into a factor on the daily price. The **"Default scale"** is
supplied:

| Rental days | 1 | 2 | 3 | 4 | 5 | 6 | 7 | each further day |
|---|---|---|---|---|---|---|---|---|
| Factor | 1.0 | 1.5 | 1.75 | 2.0 | 2.4 | 2.75 | 3.5 | + 0.3 |

So a spotlight at €20 per day costs €20 × 1.5 = €30 for two rental days,
and €20 × 3.8 = €76 for eight rental days.

If your installation is an older one, an existing "Default scale"
has not been changed – it keeps calculating with 1 /
1.5 / 2 / 2.5 and + 0.5. If you want the new factors, enter them under
Settings → Rental scales (section 16, "Master data").

Under **Settings → Rental scales** you change the table or create
further ones (this needs the "Edit rental scales" right). Which scale
applies:

- that of the product's **category**, if one is entered there,
- otherwise the **default scale**,
- unless the product names an **own scale** or **no scale** (then every
  day counts in full).

**Changed scales and existing projects.** A line remembers the state of
the scale it was calculated with. If you change the table, existing
projects keep their prices. The planning page points this out and offers
to "Switch to the current scale"; afterwards it shows the whole planning
again straight away. There is a similar note for changed product prices
(section 8, "Changed products").

### Kits

A kit bundles products that go out together: the "active speaker kit" made
of a speaker, a stand and a cable. Create a product of the **kit** type
and add the products with their quantity on its page under **"Components
of the kit"**.

- A kit has **one price** – regardless of the prices of the parts.
- The components **can still be rented individually**.
- A kit's **availability** results from the scarcest component: four
  speakers, but only three stands free – three kits.
- The **packing list** shows the components, not the kit: speakers, stands and
  cables are packed.

### Consumables and minimum stock

Gaffer tape, batteries, fluid for the fog machine: whatever is sold or used
up is a **sale or consumable** product, usually in the Verkauf (V, sale)
category. On **issue** it leaves the stock for good – it does not come back
and therefore does not appear on the packing list for taking back.

So that nothing runs out, you enter a **minimum stock** on the product. If
the stock falls below it – after an issue or during the daily check –, the
warehouse receives a notification ("Below the minimum: V-010 Gaffa-Tape
schwarz", with stock and minimum stock), once, until there is enough again.
The product's page then shows "below the minimum stock", and the **"Below
the minimum stock"** tick box in the product list shows everything that
should be reordered. Left empty, there is no warning.

### Stock and availability of a product

A product's page has two tabs. **Product** shows

- under **Availability**: for a period of your choice, how much is present,
  firmly reserved, optionally reserved and free – and which projects book
  it. The figures follow the period at once as you change it in
  the fields or in the calendar; "Check period" remains only without
  JavaScript. **"Show in the material utilization"** below opens Planning
  → Material utilisation with exactly this product and period – up to ten
  days in hours, longer ones in weeks (section 15, "Material
  utilisation"). The box and the "Timeline" tab are there only for whoever
  has the special right "See availability of material";
- under **Assigned material**: the items the stock results from. With "New
  material model" you create a model for the product; you search for an
  existing model without a product in the "Search a model without product"
  field and take it over with **"Assign existing model"** (this needs the
  right to edit material). **The search finds what you
  mean:** click into the field, and the first models without a product are
  suggested at once; type words and they may be spread over the fields –
  "Martin MAC" finds the "MAC Aura" of the manufacturer Martin; name, short
  name, manufacturer and category are searched. A model that matches but
  already belongs to a product is named at the end, greyed out and not
  selectable ("belongs to K-005 already") – so you see why it is missing; and
  if nothing matches, the list says "No model found. Only models without
  product can be assigned." If the model belongs to a different main
  category, Rentalars points this out (section 4, "Assigning material to a
  product"). Only rental and sale products have material, and
  vehicles – for them the box is called "Vehicles", and instead of the
  availability their bookings are shown in the utilization of the fleet
  (section 4, "Fleet");
- the box **"Calendar link"**: the bookings of the product as
  a calendar to subscribe to (section 4, "Calendar link");
- the box **"Accessories and replacements"** (below).

**Timeline** shows the same over weeks: at the top, for each day, how many
pieces are free (small next to it, what options would take in addition),
below that one bar per project – firmly reserved or as an option, even if
the product sits in a kit or case. That way you see at a glance when things
get tight and when something is free. It is operated as on the item
(section 4, "Timeline").

In the product list, "2 / 6 pcs." means: six present, two of them plannable
individually (the rest is permanently installed, defective or blocked).

### Products of several pieces

Some things are rented in numbers that you see as one unit: ten XLR cables
1.5 m as "Cable pack K-005". You enter **"Pieces per product"**
on the product for this (rental and sale products only, whole number,
default 1). The model stays the single cable; Rentalars converts into
pieces:

- **Stock:** ready-for-use items divided by the number of pieces, rounded
  down – 105 cables are 10 packs, if one cable fails it is 9. The product
  list shows "105 items" and a column "Pieces per product"; the product
  says "Consists of 10 × XLR cable 1.5 m", the model "One item of the product
  K-005 consists of 10 pieces of this model."
- **Planning and availability:** "3 × K-005" reserves 30 cables; blocked
  periods cut at the start and the end, leftover cables do not cover a block;
  loose contents of a case are rounded up to whole packs.
- **Packing:** for each unit that many items are chosen and issued; the row
  says "10 pieces each" and "15 of 20 items chosen"; Rentalars chooses by
  itself when exactly one unit is left or the whole stock goes out. The
  row's weight is weight × pieces. Sold packs take whole packs out of the
  stock.
- **Evaluation:** the earning per item (section 4, "What an item earns") is
  the line amount divided by quantity × pieces; wishes (shortage) compare
  items.

The number cannot be changed while items of the product are chosen on a
packing list or out, or while lines of the product stand in projects that
are not finished – their quantities would change silently. It cannot be
**lowered below the number of wished items** of a line either: Rentalars
refuses and names the lines ("2027-0003 (3 items, 2 pieces)"); take the extra
wishes out first. When you duplicate a project or copy a group, the copy keeps
only as many wishes as its pieces can carry. If a single
item falls into a blocked period, planning loses a whole pack only if that
really leaves one pack fewer. Not supported: container products with more than one
piece; the MVR import assumes one fixture per product. Not affected:
inspections, labels, defects, handover, minimum stock (items) and kits
(they take the pack product's number). Import and export have the column
"Stück je Produkt"; the API `pieces_per_product`.

### Accessories and replacements

The cable that belongs with the speaker, the stand with the spotlight – and
what can stand in when a product runs short. You name this once
on the product, and the planning of every project then reminds you. It is a
**hint and never in the way**: nothing is added by itself, nothing blocked.

**On the product's page**, in the box **"Accessories and replacements"**
(changing needs the right to edit products; everyone else sees the box once
something is entered):

- **Accessories** are products that go with this one. For each you enter
  **"Pieces per piece"** – how many go with one piece of this product, so
  that 6 speakers with 1 cable per speaker suggest 6 cables –, a note, and
  whether it is **"Required"** (the product cannot be used without it) or
  only recommended.
- **Replacements** are products that can stand in when this one is short, with
  the pieces per missing piece. A replacement is never "required". Kits have
  accessories but no replacements.
- Under **"Add product"** you look up the product, choose the **kind**
  (accessory or replacement), the pieces and the note and click **"Add"**;
  **"Replacement also the other way round"** adds the relation for the other
  product too. The arrows move an entry up and down – the planning suggests in
  this order – and **"Remove"** deletes it. Below you see where this product is
  itself named ("This product is named as accessory or replacement at: …").
- Only rental and sale products and kits can have accessories and replacements.
  A product cannot be its own accessory, and customer material only goes with
  material of the same customer.

The **page of a material model** shows the accessories and replacements of its
product, read-only, with a link to edit them on the product.

**In the planning** (section 7, "Accessories and replacements in the
planning") a panel **"Suggestions for the planning"** appears above the
lines as soon as it has something to say.

### Deactivating instead of deleting

A product that occurs in projects cannot be deleted – old projects have to
stay readable. **Deactivate** it: it stays visible in old projects but can
no longer be planned anew; its calendar link ends as well
(section 4, "Calendar link"). You delete the service product of a job function
together with its job function (section 12, "Job functions").

### Customer material – storing and taking along a customer's material

You look after a band, store their mixing desk and multicores at your place
and take them along to their gigs, where you rent out your own material and
help set up? Then you keep the band's material as **customer material**:
like your own, with model, weight, dimensions and storage location, if you
wish with items, IDs and labels – but as the **customer's property**. It
never has a price, is never rented to others and can only be planned in
this customer's projects. In the offer it appears without a price with the
note that it is taken along, on the packing list with weight and volume.

**Setting up.** Once per device or group of devices:

1. Open the customer and, in the **"Customer's material in the warehouse"**
   section, click **"Add material"**. The product form comes with category
   C **"Customer material"**, the next article number
   (such as `C-001`) and the customer as **owner**. It works the same way
   via Material management → Products → "New product": choose category C,
   type in the owner – name, customer number or town; you can also create
   the customer anew there.
2. Enter a name, for example "Mischpult Band Nordlicht". Instead of asking
   for prices, the form only asks for the owner: customer material has no
   price, no sale price, no surcharge, no scale and no discount. It is a
   rental product – or a kit made of products of the same customer; it
   never goes into your own kits. "Save".
3. As usual, create a **model** for it, with weight and dimensions, and
   assign it to the product (section 4, "Creating new material") – as bulk
   material without individual IDs ("8 × Multicore 30 m") or with items,
   IDs, storage location and labels, just like your own material.

**Where it appears:**

- The **customer's** page lists everything that belongs to them under
  "Customer's material in the warehouse", with stock and storage location.
- **Product**, **model** and **items** carry "Owned by …" and the
  "Customer material" label; instead of a price the product page says
  "Customer material, never charged. Planned only in projects of this
  customer." The **labels** name the customer instead of your company name
  (section 4, "Labels"). Inspections, defects and blocked periods are
  available as for your own material; a defect report becomes a service
  case for the customer (section 4, "Report defect").
- In the **product list** you filter under "Owner" by own material,
  customer material or a particular customer; you show the "Owner" column
  via "Columns". It goes into the export and is read back in on import,
  with customer number or name (section 16, "Import and export").

**In the project** you plan it like any other material via the field under
a group. The search only offers it in the owner's projects and their
subprojects, with the note "Customer material"; in another customer's
project Rentalars rejects it. The line carries the label **"customer
material – taken along"** and "not charged" instead of an amount. It gets
no discount – not even the customer's default discount –, cannot be
optional, an alternative or sold, and counts in no total, not in the tax
and not in the revenue from material.

- **Availability:** Rentalars checks it as for your own material – an item
  is defective, the band has a second gig at the same time. A shortfall,
  however, comes without "Subrent": nobody else can supply customer
  material.
- **Offer and order confirmation** list it in its place, with quantity,
  without price and amount, with the note "Customer's own material – taken
  along, not charged" – even an "only groups" offer names it under its
  group. That way the customer knows their things are on site. The
  **delivery note** lists it with "Customer's own material – taken along";
  the **invoice** and XRechnung leave it out.
- **Price overview** (page, PDF and CSV): with the label and "not charged"
  instead of the price columns.
- **Packing list** (screen and PDF): with weight, volume and storage location
  and the note "customer material – taken along"; the weight counts towards
  the load. Packing, issue and return work as usual.
- As long as customer material is planned in the project, the **project's
  customer cannot be changed**. It does not come along into another
  customer's project: if you apply a template there that contains it,
  Rentalars leaves it out and says so ("customer material of another
  customer: …").

**Further categories.** If C is not enough for you – for example because
you want to separate the customers' sound and lighting –, create a further
main category with stock of its own and tick **"Customer material"** on it
(Settings → Categories and codes; section 16, "Master data"). Its
subcategories follow it. The tick can only be changed as long as the
category has no products.

**A customer with material in the warehouse** cannot be deleted, only
deactivated. A product's owner can only be changed as long as it is not
planned in any project.

---

## 6. Customers

**Customers → New customer.** Company or private individual, billing
address, e-mail, phone. Rentalars assigns the customer number.

On the customer's page:

- **Billing address** with the commercial details (below), with "Route in
  Google Maps" and "Show map" (below, "Route and map");
- **Further addresses** for billing and delivery (below), each with its
  "Route in Google Maps" link;
- create **contacts**, with salutation, first name, last name, position,
  e-mail and phone; one of them can be the main contact. In the project you
  choose who is responsible for this event. See below, "Contacts: first
  name, last name and greeting in mails".
- The customer's **projects**, and the "New project" button for this
  customer.
- **Customer's material in the warehouse** – what they store with you, with
  stock and storage location, and the "Add material" button (section 5,
  "Customer material").
- **History** of all changes.

You can also enter a new customer straight away when creating a project,
without leaving the project form (section 7, "Creating a project").

**Who sees the customer's name.** Everyone who may see a
project or a service case sees the **customer's name** – in the project
list, in the lists of service cases, on the pages, on the packing list, in
the search by name and in the interface (`customer_name`), crew and
freelancers too. The name is a **link** only for those who may read
customers; for the others it is plain text. Everything else stays with the
right on customers: contact persons, phone and e-mail, "Reported by", the
customer's page with its projects. Calendars and the deployment PDF still
name no customer.

Many customers at once – for example from your previous program or from
Lexware – you take over with "Import" above the customer list (section 16,
"Import and export").

### Contacts: first name, last name and greeting in mails

A contact has a **first name** (optional) and a **last name**
(required) instead of one name; "New contact" opens a whole page with
salutation (suggestions Herr, Frau, Dr., Prof., Prof. Dr.), first name, last
name, position, e-mail, phone and "Main contact". The name in lists, search,
exports, documents and recipient lists stays the composed one; sorting is by
last name, then first name. If you type only one name in an import or via the
API, Rentalars splits it: the last word is the last name, "von", "van", "de",
"der", "zu", "zur" stay with the last name, "Berg, Anna" is recognised, a
single word is the last name. A leading salutation ("Frau Müller", "Mr
Berg") becomes the salutation (or is dropped if one is entered already), text
in parentheses is dropped, a remark after a comma ("Anna Berg, Technik")
becomes the position if that is empty. First and last name together may be
at most 200 characters long. Existing names were
split this way – a name with a title such as "Dr. Anna Berg" gives the first
name "Dr. Anna"; move the title to the salutation if you like.

**The greeting in e-mails** is set per contact in the section "Anrede in
E-Mails" of the form; a preview shows how it reads, and the customer page has
a column for it:

- **formal** (default): "Sehr geehrte Frau Berg," / "Sehr geehrter Herr
  Berg," – by the salutation Frau/Herr (English Ms/Mr); a title without
  gender ("Dr.") gives "Guten Tag Dr. Berg,"; with no salutation at all
  "Guten Tag Anna Berg,";
- **personal:** "Hallo Anna," – titles dropped; without a first name it
  becomes formal;
- **own text:** verbatim what you write.

The greeting is used in new e-mails, in the answer and in the mail for a
document – when exactly one recipient is chosen and he or she is a contact of
the customer of this project –, in the AI's draft (verbatim) and, as
`{greeting}` or `{anrede}`, in the texts of documents and of the automatic
reply to enquiries. Not built: a default greeting for the whole company; the
"To" buttons in the mail form do not change the greeting if used after
writing.

### Does the customer already exist?

When you create a customer, Rentalars compares the name and e-mail address
with the existing customers while you are still typing. If there is one
with a similar name or the same e-mail address, **"This customer may exist
already:"** appears with name, customer number, town and the reason
("similar name", "same e-mail address"). A click opens it in a new window.

If it really is the same one, you carry on working with the existing one.
If it is a different one – two companies called "Müller GmbH" in different
towns –, you tick **"Create anyway – it is a different customer"** when
saving. Without this tick Rentalars does not create a second one.

### Commercial details

In the customer's form ("Edit customer"):

- **VAT ID** – with country code, without spaces, e.g. `DE123456789`
  (Rentalars removes spaces itself). It appears on the order confirmation
  and invoice as "Your VAT ID". If the customer has a VAT ID of another EU country and the tax rate 0 % applies to the service, the invoice carries, the note that the recipient owes the tax (reverse charge) instead of "Exempt from VAT"; the e-invoice names the category AE and needs the VAT ID of your company. This does not apply to small businesses (§ 19 UStG, setting in the bookkeeping) or to customers in Northern Ireland (XI); a sale of goods to a business in another EU country (intra-Community supply) is not this case – clear it with your tax adviser.
- **Tax number** – for example for customers without a VAT ID; the import
  from Lexware brings it along.
- **Leitweg-ID or buyer reference** – for invoices to public authorities
  the Leitweg-ID, otherwise a reference the customer requires on their
  invoices. Rentalars puts it into the XRechnung as the buyer reference
  (section 11); if it is empty, the project number appears there.
- **Payment terms in days** – how long the customer has to pay an invoice.
  Left empty, the payment term from the company data applies (section 16).
- **Default discount in percent** – goes into every new material line you
  add in their projects and can still be changed there per line. It does
  not change existing lines. Only those who may see prices may see and
  change it; for everyone else the field does not exist.

### Several addresses

The address on the customer is their **main address** and remains the
billing address if nothing else is chosen. In addition, a customer can
have any number of **further addresses** – accounting at head office, the
northern warehouse as delivery address.

**Further addresses → New address:** type (**billing address** or
**delivery address**), a label ("Lager Nord"), name or company (empty: the
customer's name), addition ("department, c/o …") and the postal address.
With **"default"** it becomes the default address of its type; there is
one per type.

**In the project.** A new project takes over its customer's default
addresses by itself – whether you choose the customer in the form, create
the project via "New project" on the customer's page or another program
creates it via the API. Under "Edit project" you can then choose a
different **billing address** and **delivery address** from the
customer's further addresses; the fields appear if the customer has such
addresses.

- The billing address appears on the order confirmation and invoice.
  Empty: the customer's address.
- The delivery address appears on the delivery note. Empty: the venue,
  otherwise the customer's address.

If a project's customer changes, the previous customer's addresses no
longer fit: the new customer's default addresses take their place.

### Deleting and anonymising

A customer without projects can be deleted – unless they have material in
your warehouse (section 5, "Customer material"); then you deactivate them.
If they have projects, these are kept as business transactions; the
customer can then be **anonymised** ("Anonymise customer" at the bottom of
their page): name, address, contact details and note are overwritten, all
contacts deleted, and the old details also disappear from the change log.
Customer number and projects remain with their figures. This is intended
for deletion requests and **cannot be undone**. A customer who merely
should no longer appear in selection lists is set to not active instead
(untick "Active"). With an anonymised customer, the mails that came from
them or went to them disappear too (section 14). The AI
summaries of the customer's projects, with their earlier versions, go as
well, and no automatic summary is made for the customer again (section
14, "Automatic summaries at night"). Anyone who does not want automatic
summaries for a customer who has not been anonymised can exclude them
(same section).

### Venues

**Customers → Venues.** Halls, clubs, open-air sites where you work
frequently, with everything the crew needs to know: postal address,
**contact on site** with phone, **access and loading** (loading zone,
clearance height, parking, keys), **power** (connections, fusing,
distances), notes and a **hall plan** as a PDF or picture.

In the project you type the venue into the "Venue" field and choose it from
the suggestions; you create a new one right there in the dialog (section 7,
"Creating a project"). The "Place, free text" field takes additions such
as "Halle 3" – or a place that does not deserve master data. In the
project's header the venue's name leads to its page; its notes appear on
the project's "Overview" tab, which the crew sees too (section 12). A venue
named by projects cannot be deleted, only deactivated. On its page "Route
in Google Maps" leads from wherever you are right now to the venue, and
"Show map" shows where it is (just below).

### Route and map

Every postal address – venue, customer and their further addresses,
supplier (on the "Subrental at …" page, section 9), your company under
Settings → Company data and settings – has the **"Route in Google
Maps"** link. It opens Google Maps route planning in a new tab and always
starts at your current location – for every address, including venues,
delivery addresses and suppliers. For trips with intermediate stops the
stops are kept (section 7, "The trips of a project"). The address only
leaves Rentalars with this click. Rentalars calculates a distance only if
your administrator has set up the route service – and then only as a
suggestion for the kilometres of a vehicle on a trip (section 7,
"Logistics").

**The map.** Below the address is **"Show map"**. Only with that click does
Rentalars ask OpenStreetMap where the address is – once per address; it
remembers the answer –, and your browser loads the map from OpenStreetMap.
Nothing goes out before that. With the map images your browser sends the
address of your installation (only scheme and host, without path) to
OpenStreetMap – its usage policy requires this. You zoom the map with "+"
and "−", on the phone with two fingers, with the mouse wheel only once you
have clicked into the map – otherwise it would zoom along when you scroll
the page; at the bottom right it says "© OpenStreetMap contributors".
Every address has a numbered marker. Below the map, for each address, it
says where its position comes from: "Position from OpenStreetMap",
"Position set by hand" or "Not found on the map."

**If a marker is in the wrong place** – a new hall, an address that
OpenStreetMap does not know –, open **"Correct the position"** below it:
click into the map, drag the marker or enter latitude and longitude (the
way with the keyboard), then **"Save position"**. The position applies to
everything with the same address – including projects and customers that
name this place. **"Look it up again"** discards the position and asks
OpenStreetMap again. Anyone who may change the record the map belongs to
may correct it – for a project, whoever may edit it; the change appears in
its history.

A project's map appears with its trips, on the schedule tab and in the
overview (section 7, "Schedule"). If you always want to see the maps
straight away, switch on **"load maps at once"** under Settings →
Company data and settings; then every address goes to OpenStreetMap as soon
as the page is opened. If your administrator has switched the maps off in
the configuration, there are only the links to Google Maps.

---

## 7. Planning projects

### Creating a project

**"Projects" → "New project".** Name and customer are required; Rentalars
assigns the project number. If there are project templates, the field
**"Template"** is at the top: if you choose one, the groups, lines, crew
lines and schedule of the template are added when you save (below, "Project
templates"). For a rental without personnel there is the template
"Dry Hire (rental without crew)" (below, "Dry hire – rental without
personnel").

**The project number** consists of the year and a running number:
`2026-0042`. Counting starts again at 0001 each year. Subprojects carry the
number of their whole project with a number appended: `2026-0042-1`,
`2026-0042-2`. An administrator sets the prefix under "Settings" → "Number
ranges" (section 16); a change only applies to new projects.

**Numbers with "P-".** Project numbers do not begin with "P-" (as in `P-2026-0042`);
a number with "P-" is understood all the same. It is shown in the head of the project after
today's number – "(formerly P-2026-0042)" – and works: in the search, in
the filter of the project list, wherever you enter a project number (for
instance when moving or taking over a mail), in links and bookmarks
(they lead to today's address) and in replies to mails with the tag
`[RL#P-2026-0042]` – such mails land in the project as usual (section 14).
Documents already made stay as they were sent, with the number the project
had at the time; new documents show today's number. If your installation
uses its own prefix with letters, such as `PRJ-{year}-`, it stays as it is.

**Customer and venue by typing.** Instead of picking from a long list, you
choose the customer by typing a few letters of the name, customer number or
town and taking one of the suggestions. If the customer does not exist yet,
the last suggestion reads something like **Create "Müller GmbH" as a new
customer**. It opens the customer form in a dialog, with what you typed as
the name and with the same warning about duplicates as under customers
(section 6, "Does the customer already exist?"). After "Save customer" the
new customer is in the project, and you are still in the project form.
The same goes for the field **"Venue"**: type the name or town, or, as the
last suggestion, **Create "…" as a new venue**. Anyone who may edit
customers can create new ones.

**Creating a contact person**. The field **"Contact"** lists the contacts of the chosen customer; the last choice is
**"+ New contact person …"**, as soon as a customer is chosen and you may edit customers. It opens a dialog with salutation, first
name, last name (required), position, e-mail and phone; after "Save contact person" the person is chosen in the field, and nothing
in the project form is lost. The first contact of a customer becomes its primary contact; the greeting in mails and further details are
kept on the customer's page. This works in the form for a new project, when editing, for a subproject and when turning a service case
into a project, and in the form "New service case" and when editing a service case. The choice is missing for an anonymised customer; a double click does not add the same person twice.

If the customer has default addresses for billing and delivery, the project
takes them over; you choose a different one under "Edit project" (section
6, "Several addresses").

**Internal project.** With the tick box "internal project" a project needs
no customer. It is meant for time that belongs to no customer project –
warehouse, workshop, office. Everyone who records time can book onto it
(section 13). The simplest is to create one that runs all year.

A project has **two periods**. The form names them after what they decide,
and the difference matters:

| In the form | Fields | Meaning | What for |
|---|---|---|---|
| **"Rental period: material out of the warehouse"** | "material out from", "material back by" | from leaving the warehouse until it comes back, setup and teardown included | decides **availability**; the lines take it over |
| **"Event – for the rental days charged"** | "event from", "event until", "rental days" | optional: the days of the event itself, for instance the show days | only suggests the **rental days** that are charged |

**Only the rental period decides when the material is taken.** A wedding on
Saturday from 15:00 to 02:00 is *one* rental day. But the material leaves the
warehouse on Friday and comes back on Monday – for all that time it is not
available for other projects. You may leave the event period empty; it
changes nothing about availability.

Both boxes are laid out the same way: "from", "until" and **"Choose the
period in the calendar"** in one row, with the rental days below for the
event; in narrow windows the button moves below the fields. In the
calendar of the rental period the event is hatched as soon as you have
entered it, and the other way round – so while choosing you see straight
away how the two relate to each other (section 2, "Entering periods").

**Usual times: 12:00 to 12:00.** A new project suggests tomorrow 12:00
to the day after tomorrow 12:00 as the rental period. You change the times
under "Settings" → "Company data and settings" ("usual start time", "usual
end time").

**Rental days** are the days that are charged. If you leave the field
empty, Rentalars works them out from the event period – or, if there is
none, from the rental period: every 24 hours begun count as one day. You
can enter any other value – what you charge is your decision.

**Events in several parts** – setup on Thursday, show on Friday and
Saturday – are not entered as several event periods but as **phases** in
the tab "Schedule" (setup, show day 1, show day 2 …; below, "Schedule"). The
rental period covers everything; you enter the rental days the way you
charge them.

**Projects from before Rentalars.** You have written invoices for years that
were never in Rentalars? You can take them over as closed
projects, straight from the invoice PDFs (section 11, "Importing old projects
from invoices"). A customer's history is then complete in
Rentalars – and nothing is reserved, no mail is sent, and the numbers of your
running documents stay untouched.

### The status

The status says how binding the project is – and that decides whether it
blocks material for others.

| Status | Meaning | Reserves material? |
|---|---|---|
| **Inquiry** | someone has asked | no |
| **Option** | customer is interested, has not committed yet | **pencilled in**: visible to others, but takes nothing away |
| **Confirmed – details open** | committed, details still missing | **firm** |
| **Confirmed** | committed | **firm** |
| **Out** | all material has been handed out | **firm** |
| **Returned** | material is back | no |
| **Closed** | done; can no longer be changed | no |
| **Cancelled** | will not take place | no |

You change the status at the top in the head of the project, on every tab:
in the list **"Change status to …"** choose the new status and click
**"Change status"**. The list only offers sensible next steps; before
"Cancelled" Rentalars asks you to confirm. You stay on the tab you were on
(below, "The head of a project").

"Returned" is so named that
nobody confuses it with the button "← Back" (section 2).

You do not have to set "Out" and "Returned" by hand: Rentalars sets "Out"
as soon as **all** material of the project has been handed out – with
several packing lists, when all of them have been handed out – and "Returned"
as soon as the return is complete – automatically, when everything is back
with "Book the return" – and no packing list is still out or waiting to be
handed out (section 10). If only part of it is out, the project keeps its
status, for example "Confirmed". The material handed out is still out
nonetheless and not free for other projects. If you want to set the project
to "Out" earlier, you can do that by hand; "Inquiry", "Option" and
"Cancelled" cannot be set while material is out.

A **closed** project can no longer be changed – only whether it has an
invoice can still be noted (section 11, "Invoices still to be written").
Only someone with the right "Reopen closed projects" may open it again.

Only inquiries, options and cancelled projects can be **deleted**. A
confirmed project is cancelled, not deleted – that way what happened stays
traceable.

### The head of a project

The page of a project has ten tabs: **Overview**, **Planning**, **Price
overview**, **Documents** – straight after the prices they are made from, and
with the files of the project –, **Schedule**, **Packing list**,
**Correspondence**, **Chat**, **Access**, **History**.
**The overview is the first tab**, as in a service case, and
it is where you land when you open a project from a list, the start page,
search, a calendar, the customer page or a notification (address
`/projects/<no>/overview/`). The planning stays under "Planning"
(`/projects/<no>/`); saved links, jumps to shortages and the return after a
planning action still lead there. Someone who is only planned in and may
plan nothing else sees "You are not planned in" in the personal box of the
overview as long as they are not planned in. Someone who is only planned in sees "Packing list", "Chat" and
"Overview" of these and, – once they have accepted or are
planned firmly – "Correspondence" with the open messages (section 12);
otherwise "Correspondence" only those who may read mails (section 14);
"Price overview" only those who may see prices. A whole project and its
subprojects have the tab **Subprojects** straight after "Planning" (below,
"Subprojects"). A service case has fewer tabs (below, "Service cases").

At the very top is the project number. Above the tabs are the status,
customer, period, venue and the **code** of the project for the subject of
mails, for instance `[RL#2026-0042]` – one click copies it –, and below that
a **follow-up**, if there is one (below). From "Returned" on,
it also shows everyone who may see prices the state of the **invoice** –
"Invoice RE-…", "Invoice issued", "No invoice" or "Invoice open" (section
11, "Invoices still to be written"). To the right are the actions, the
same on every tab and always in this order:

- **"Edit project"** – name, customer, periods, addresses (above, "Creating
  a project").
- **Status:** in the list "Change status to …" choose the new status and
  click "Change status". The list only offers what is possible from the
  current status; the button can only be pressed once you have chosen a
  status. Before "Cancelled" Rentalars asks you to confirm. For a project
  with subprojects, "subprojects too" is next to it (below,
  "Subprojects"). You stay on the tab you were on – only "Confirmed –
  details open" without open items takes you to the schedule, so that you
  note them down.
- **Make a document:** the button suggests what comes next – for an
  inquiry or option "Make offer", for a confirmed project "Make order
  confirmation", while out "Make delivery note", when returned or closed
  "Make invoice". Behind the arrow ▾ are the other documents. The button
  opens the tab "Documents" with the chosen document in the box "Make a
  document"; there you see the draft and make it (section 11). So a click
  in the head does not make anything yet. A subproject gets its offer,
  order confirmation and invoice via its whole project, and without the
  price right there are no documents with prices – then the button
  suggests the delivery note for a confirmed or running project, and
  nothing otherwise; the list behind the arrow stays. If "make invoices in
  Rentalars" is off (section 11), it suggests no invoice, and there is none
  behind the arrow.
- **"Follow-up"** – have the project brought up again on a certain day
  (below, "Follow-up"). If it already has one, the button is missing; the
  follow-up is then shown with "Change" and "Done" below the details of the
  head.
- **"Duplicate"**, **"Save as template"**, **"Add subproject"** – behind
  its arrow ▾ **"Divide into subprojects"**, on a whole project **"Turn
  groups into subprojects"** (below, "Subprojects").

What you are not allowed to do is missing: status, documents and follow-up
only with the right to edit the project, "Edit project" only as long as it
is not closed.

### Follow-up

Chase up an offer, ask the customer about setup times: with **"Follow-up"**
in the head of the project, Rentalars brings the project up again on a
certain day. In the dialog you choose **"Follow-up on"** – the day –, if you
like a **"Time"**, **"For"** – you are preselected; anyone who
may open the project can be chosen – and, if you like, write a **"Note"**,
such as "Angebot nachfassen"; "Save follow-up". This works in every status,
even for closed projects, since it changes nothing about the planning. It
is typical for inquiries and options.

- **On the day** the person gets the notification "Follow-up: …" – without
  a time from 06:00, with a time from that time (even before
  06:00). Only then does the follow-up count as due – in the head, on the
  start page, in the project list and for the automation "a follow-up is due".
  The notification comes in Rentalars and, as set under "My account" →
  "Notifications" for "Follow-up of a project" (on by default), by mail and
  in the companion app. A day that is already past is due at once. If the
  person has been deactivated in the meantime, the notification goes to the
  project manager. If you only change the note, no new one comes; a new
  day, a new time or a different person gets one.
- **In the head of the project** it is shown until it is done – "Follow-up
  on Tue 20/10/2026 at 14:30 for Anna Becker – Angebot nachfassen", from its
  time on with "due" –, for everyone who may read the planning; with
  "Change" and "Done" for everyone who may edit the project.
- **On the start page**, under "Your follow-ups", are the due ones that are
  for you (section 2, "Start page and search"); "All my follow-ups" leads to
  "Planning" → "Follow-ups".
- **Under "Planning" → "Follow-ups"** all follow-ups of projects and service
  cases are listed in one table (section 15, "Follow-ups").
- **In the project list** it is shown under the name of the project. The
  filter **"Follow-up"** shows "due", "for me" or "all with follow-up" –
  across all statuses, like a search –, and you show the column
  "Follow-up" via "Columns" to sort by it. Filter, column and note in the
  list are only seen by those who may also see the customers; the crew sees
  no follow-ups.
- **In the calendar** with the tick box "Follow-ups" above
  the calendar (section 15, "Calendar").

**"Done"** takes the follow-up off the project. Setting, changing and
completing are recorded in the history of the project.

### Related projects and service cases

The complaint about the city festival, the service case about the console
that failed at the customer's, the follow-up project next year: you relate projects and service cases to each other. A project or service case can be related to any number
of others; the relation holds in both directions and shows on both.

The box **"Related"** is on the **Overview** of a project and on the
**page of a service case** – for everyone who may read the planning or
works on the service case. It is small and discreet: a heading
and one line per entry with number, name, kind (project or service case),
status and the note, with a link; the form for linking opens only under
"Add a related one". If you may not open
the other project, it only says "Project 2027-0042 (no access)" – without
name, status, note and link.

- **Link:** under **"Project or service case"** type the number or name and
  choose from the suggestions (without JavaScript the full number),
  optionally a **"Note (optional)"** such as "complaint about …", then
  **"Link"**. This needs edit access to this project and read access to
  the other one.
- **Unlink:** **"Unlink"** in the row, after a confirmation – with edit
  access here and read access there.

Relations are always between whole projects and service cases; a
subproject shows the box only if it already has entries – link its whole
project. Linking and unlinking are recorded in the history of both sides.
Duplicating takes over no relations; a service case turned into a project
keeps them.

### The planning page

The planning shows the lines, group by group, below them the lines without
a group, the **personnel**, the **logistics** (below,
"Logistics"), the surcharges and the totals. Each row shows
quantity, product, **availability** and – with the price right – rental
days, unit price and amount.

**The planning follows the stock**. You link a product with a
material model in a second tab, an item is blocked, someone else plans the
same material – the **availability column**, the
**hints on wishes** ("Wish: …") and the **notes above the lines** of the
planning you left open in the first tab update
themselves: as soon as you come back to the tab
and otherwise with the other changes of the page, within about 20 seconds.
Between two refreshes there are **at least 20 seconds**; if another change
comes in meanwhile, exactly one more refresh follows. A cell you are standing
in is left as it is and updated later; a request that hangs for more than
15 seconds is given up, and the tab asks again next time.
Only these cells change; the page is not reloaded, so **what you have typed,
the scroll position, open dialogs and the focus stay**. Whoever lacks the
special right "See availability of material" has no such columns and nothing to
refresh. Not covered: ticking off on a packing list; a change of your own in
this tab updates its cells at once.

**Saving keeps your place**. Saving a group, a subgroup or a
line does not jump to the top of the page, and sections you had opened or
folded stay as they were.

#### Adding a line

Below each group (and below "Without group") there is a field:
**"Add: article number, product, model or item ID".**

1. Type a few characters – `K-005` or `xlr`. A list suggests products,
   with their stock.
2. Choose with a mouse click or the arrow keys and Enter.
3. Enter the quantity, press Enter or "Add".

The line appears at once, with price and traffic light. The period of the
line is initially that of the project. **Customer material** – what a
customer stores with you – is only suggested by the field in projects of
that customer; it is then shown without a price with "customer material –
taken along" (section 5, "Customer material"). **Incidental costs** –
transport, travel costs, fees – are added here just like material.

The field does not suggest **services**: you plan personnel in the block
"Personnel" via their job function, and the crew line takes over the price
of its service product (section 12, "Planning personnel in a project").
If you type in a service anyway, Rentalars refuses it with this hint.
Older material lines with a service stay as
they are – with price and on documents already made –, but carry the hint
"service – plan under Personnel"; for new deployments you plan the job
function in the block Personnel.

The field does not suggest **vehicles and trailers** either:
you book them in the block "Logistics" (below, "Logistics"). If you type
one in anyway, Rentalars refuses it ("… is a vehicle. Vehicles and
trailers are booked under Logistics.").

**A particular model or item.** The field also finds models ("Robe
Pointe", "Sennheiser") and single items (the ID `0742` or a serial number).
If you choose such a hit, the line is created for the corresponding product
– and the model or item is attached to it as a **wish**. The wish is an
internal hint for the warehouse: it appears on the line and on the
packing list, not in the price overview, and it changes neither price nor
availability. Rentalars warns you if the wished-for item is defective,
permanently installed or already wished for elsewhere in the same period.

**"Scan items"**, next to "Line without product", opens the
scan window (section 4, "Scanning labels and codes") and stays open: every
item whose label you read is added as a line of 1 for its product, without a
group, with exactly this item as wish. "Added: …" confirms it; a code that
is no item or whose product cannot be planned is named ("… cannot be
planned."). The camera is optional; a hand scanner or typing the ID works in
the same window.

**A wish for one piece of a pack**. A product of several
pieces (section 5, "Products of several pieces") – say "Cable pack" of ten
cables – is one line of quantity 1. If you wish for one particular cable, the
line stays at **1 pack**, and the wish counts as **one piece of it**: the line
shows "Wish: item 0042 (Cordial CPM 5 FM) – **1 of 10 pieces**". The other nine
cables come from any items of the product, and the price does not change.
Each wished item covers one piece, so you can wish for several: in the dialog
of the line (below) enter the further IDs, and the line says "3 of 10 pieces".
More wished items than the line has pieces are refused ("3 items are wished,
but the line has only 2 pieces. Each wished item takes one piece."). If you
**delete a wished item** from the stock, the next wished item of the line moves
up into its place, so the wishes stay visible and keep counting (also for the
hints about the same item being wished in other projects). A wished item that
is **blocked** in the period of the line is reported ("… is blocked in this
period: …"); if it is retired, the wish stays and the planning warns ("Item …
is retired") – it is never deleted silently. Rentalars
does **not** split the line itself ("1 of 10" into two lines), as a pack stays
one pack for the price and the documents; if you really want a split, plan two
lines.

#### The traffic light

| Display | Meaning |
|---|---|
| 🟢 **free** | There is enough. |
| 🟡 **tight** | There is enough – but the **option** of another project wants the same material. If it is confirmed, something will be missing. |
| 🔴 **2 missing** | There is not enough; this many pieces are missing. |
| ⚪ **not checked** | Incidental costs, surcharge, subrental – nothing that can run out. |

Below it, in small print, is what this is based on:
"stock 12, elsewhere 8, optional 6" means: twelve in stock, eight of them
firmly reserved for other projects in this period, six more pencilled in by
options.

**A shortage does not stop you from saving.** You can overbook – sometimes
you simply know that more is coming. The line stays red, the top of the
page says how many pieces are missing in total, and the page
"Shortages" lists them until the gap is closed: reduce the quantity, move
the period or subrent (section 9).

The traffic light – in the planning and in a line's dialog –
and the notes about missing material are shown only to whoever has the
special right **"See availability of material"** (section 16, "Roles and
rights"). All roles supplied except Crew have it.

#### Accessories and replacements in the planning

If you have named accessories and replacements on products (section 5,
"Accessories and replacements"), a panel **"Suggestions for the planning"**
appears above the groups as soon as it has something to say. Without such
entries you see nothing of it. It loads shortly after the page and is
refreshed when the planning changes (at most 12 suggestions of each kind at
once). It waits for a moment – about 0.6 seconds without a further change –,
checks at most six replacement products per request and locks its buttons
while a request runs; a screen reader is not read every change, only a status
line when the number of suggestions changes.

- **Accessories not planned yet.** For every product of the planning that
  has accessories, the panel lists those that are neither a line nor in a
  kit of the planning: "XLR cable 5 m – goes with Speaker 12" with the label
  "required" or "recommended", the note and – with the right "See
  availability of material" – how many are free in the period. The quantity
  is the quantity of the product times the pieces per piece, rounded up:
  6 speakers with one cable each suggest 6. If **several products** of the
  planning name the same accessory, the quantities are **added up** and rounded
  up once (3 × A and 2 × B with the same cable make five, not three), and the
  accessory is "required" as soon as one of them requires it. An accessory that
  is planned already but in too small a quantity is suggested again for the
  rest. Change the number if you like and
  click **"Add"**: the line is added to the group of the line it belongs to, with
  the period of the project, and its traffic light is calculated as usual. A
  second click adds nothing twice ("… is already in the planning").
- **Replacements for a short line.** If a line is short in its period – or
  its product is deactivated –, the panel names the replacements of its
  product: "Speaker 12: 2 pieces are missing → Speaker 12b, 3 free, covers it"
  (or "only partly"), with the quantity that would stand in. **"Add
  replacement"** adds a line for it, again in the group of the short line,
  which stays as it is – you reduce it yourself. A replacement that is in the
  planning already is not suggested again. The numbers are the planning's own, judged as if the
  replacement were added. Whoever may not see availability gets no replacement
  suggestions.
- **"Dismiss"** next to a suggestion – or **"Dismiss all suggestions in this
  project"** – hides it in this project only. A note under the panel counts the
  dismissed ones ("2 suggestions are dismissed in this project") and **"Bring
  them back"** shows them again.

A suggestion never blocks anything and never adds itself. Everyone who can
read the project sees them; adding and dismissing need the right to edit the
project. When you **make an offer** (section 11, "Making a document") and choose the
kind "Offer", the same hints appear in the form as **"Accessories and
replacements to think of"**, without a button to add: if something is missing,
you go back to the planning.

#### Editing a line

At the end of each row are five icons: **optional**, **alternative**
(both below, "Optional and alternative lines"), **pencil**, **copy** and
**bin**. The pencil opens a dialog:

- **"Title"** – as it should appear on documents.
- **"Quantity"**.
- **"Group"** – moves the line.
- **"Counts as"** – normal, optional or alternative; for an alternative,
  below it **"Alternative to"** with the line it could replace (below,
  "Optional and alternative lines").
- **"From" / "Until"** – side by side in one row: a period of its own for
  this line, if it has to go out earlier or comes back later than the
  rest. Availability is checked for exactly this period; the dialog shows
  it while you type – and also how many **rental days** the period gives
  (section 8).
- **"Specific model"** and **"Specific item (ID)"** – the wish from above,
  which you can also enter or remove here later. On a line of several pieces
  (quantity above 1, or a product of several pieces) there is also **"Further
  specific items (IDs)"**: the IDs of more items, separated by commas. Each
  wished item covers one piece of the line; the others come from any item of
  the product. A further item must belong to the line's product.
- **"Note"** – appears on the packing list ("mit Torblende").
- **"Rental days"**, **"Unit price"**, **"Discount in percent"**, **"Scale
  factor by hand"** – see section 8. Only with the price right.
- **"Sell instead of renting"** – only on a line that already
  sells a rental product: it keeps its price and stays editable; if you untick
  it, the material is rented at the product's price. A rental product is
  not sold anew – that is what sale products are for (section 5,
  "Creating a product").

The bin deletes the line – after you confirm with "Yes, delete". Once its
material has been handed out, this is no longer possible.

**Duplicating a line.** The double-sheet icon in the row ("Duplicate
line") creates a copy directly below it, in the same group: with product,
quantity, period, price and discount, note, "Counts as" and wished-for
model – but not with a wished-for item, which after all exists only once.
Handy for the same spotlights in a second period or as an alternative. A
subrental that covers a shortage cannot be duplicated.

#### Several lines at once

In front of each line is a check box. Tick the lines you want to change
together; the check box in the head of a group selects all lines of that
group (likewise for "Without group" and the surcharges). As soon as a line
is selected, a bar appears at the bottom with the number of selected lines.
With it you make them

- **"Optional"** or reset them with **"No longer optional"**,
- **"Alternative to …"** another line – a window asks which one,
- under **"Move to …"**, move them to another group, also into a subgroup
  or to "without group", with "Move",
- give them a **discount** in percent ("Set discount", only with the price
  right),
- get rid of them with **"Delete"** – after you confirm.

Lines for which this is not possible stay unchanged; Rentalars names them
with the reason ("Left as they are: …") – for instance because their
material has already been handed out, because other subprojects take over
pieces of them, or because it is a subrental that belongs to another line
and moves with it. A percentage surcharge gets no discount and stays with
what it refers to. Every change is recorded in the history as usual.
**"Clear choice"** removes all ticks.

#### Optional and alternative lines

Not only a whole group, a single line too can be an additional offer or a
variant: the second fog machine, the larger screen instead of the small
one. The quickest way is with the two icons at the end of the row, in
front of the pencil:

- **optional** switches the line to optional and back again. If the icon
  has an orange outline, the line is optional.
- **alternative** opens a window: in it you choose which line the
  alternative could replace. This is required.

The same can be done in the dialog of the line under **"Counts as"**:

- **normal** – part of the project.
- **optional** – an extra the customer can add.
- **alternative** – a variant of another line, which you choose under
  "Alternative to".

An optional or alternative line carries a yellow label "optional" or
"alternative" in the planning and shows its price with the remark "not in
the total". Below an alternative is what it could replace: in the planning
and in the price overview "alternative to "8 × LED-Scheinwerfer"", in the
offer and in the order confirmation "alternative to pos. 3". If you delete
the line an alternative belongs to, the alternative becomes an optional
line. Older alternatives do not have this
information yet; if you edit one, the dialog asks for it. Such a line

- does **not** count towards the subtotal of its group or the project
  total; the totals name it separately ("Optional lines, not included",
  "Alternative lines, not included");
- **only reserves like an option**: it makes other projects "tight", but
  takes nothing away from them (section 9);
- is **not on the packing list** and **not on the invoice**;
- is marked as such in the price overview, in the offer and in the order
  confirmation (section 11).

If the customer takes it, you set it to "normal". A percentage surcharge
only applies to an optional line if it is optional itself. A subrental that
covers a shortage (it counts like its line), a line whose material has
already been handed out, and a line from which other subprojects take over
pieces cannot become optional or an alternative.

#### Groups

Groups structure a project – by trade, by stage, by day. Each has a
subtotal of its own. Groups can be **nested**, up to three levels deep:
"Licht › Front-Traverse › Traverse 1" (below, "Nested groups").

- **Create:** in the row directly below "Without group" (below, "Below the
  groups") type the name into the field "New group", next to it leave "at
  the top level" or choose "in" another group, "Add group".
- **"Edit"** (pencil in the header row of the group): name, description,
  **"Parent group"**, rental days of its own, discount or flat price
  (section 8) and **"Counts as"**:
  - **normal** – part of the project.
  - **optional** – an additional offer ("Nebel und Effekte"). Shown with a
    subtotal, but does **not** count towards the project total and only
    pencils in material.
  - **alternative** – a second variant of another group, which you choose
    under "Alternative to"; behaves like "optional". A group can only be an
    alternative to a group, not to a line, and not to a group above or
    below it.
- **Optional** and **alternative** also work more quickly, with the two
  icons in the header row of the group in front of the pencil – as for a
  line (above). The head of an alternative group then reads
  "alternative to "Licht Variante A"".
- **Copy** (double-sheet icon): creates the group again with its lines and
  subgroups, at the end of the same parent group.
- **"Delete"** (bin): lines and subgroups move up one level – into the
  parent group; for a group on the top level the lines go to "Without
  group" and the subgroups to the top level. The confirmation question
  says where.

#### Nested groups

Drag a group by the **handle** next to its name into another one, out of
it or to another place. With the keyboard: focus the handle, ↑ and ↓
change the order, → pushes the group into the one above it, ← brings it up
one level. Alternatively, in the dialog "Edit group" you choose the
**"Parent group"**; the group then moves there with its lines and
subgroups, as the last subgroup. With the arrow in front of the name you
collapse and expand subgroups. A group cannot be pushed deeper than three
levels or into itself; Rentalars says so and leaves it where it was.

- A **parent group** can have lines of its own – the lighting desk in
  "Licht", for instance. They come before its subgroups; the **"Subtotal …
  with subgroups"** is below the last subgroup.
- **Discounts:** first the discount of the subgroup applies, then that of
  the parent group to the result; a **flat price** of the parent group
  replaces everything below it (section 8).
- **Optional:** subgroups of an optional group are optional as well, those
  of an alternative group are alternatives as well – the planning says
  "optional, like the group above". A subgroup that is optional itself does
  not count towards the total of its parent group.
- **Rental days:** if a subgroup has none of its own, those of the nearest
  parent group that has some apply.

Price overview, documents, packing lists, templates and duplicating take the
structure over.

#### Sorting

Grab a line by the six dots at the start of the row and drag it to another
place – into another group too. It also works without a mouse: jump to the
six dots with the Tab key and move the line up or down with the arrow
keys. A line gets into another group via "Edit" – several at once via the
selection (above, "Several lines at once"). A subrental that covers a
shortage moves with its line. You move whole groups by their handle
(above, "Nested groups").

#### Below the groups

Directly below "Without group", above the personnel, is a row with
everything apart from products that you can add – in this order:

- **new group**: name, level, "Add group" (above, "Groups");
- **"Line without product"**, next to it **"Insert text
  line"**, and, in a whole project with subprojects, **"Take over from
  another subproject"** (below, "Subprojects");
- **"Import light plot (MVR)"** (below).

You add products themselves in the field below each group (above, "Adding
a line"). On a phone the row wraps, and the fields take the full width.

#### Line without product

For one-off things that do not deserve a product: "Bühnenpodest vom
Veranstalter", "Anfahrt Sonderfahrzeug". The button **"Line without
product"** below the groups asks for title, quantity, unit, price and tax
rate. Such lines are not checked for availability.

#### Insert text line

**"Insert text line"** inserts a line with text only – no
product, quantity, price, discount or period: a heading, a note such as
"Set-up by the organiser", a paragraph between the lines. The dialog asks
for the text and, if you like, a further text. The line appears in the
planning, offer, order confirmation, invoice, cancellation and price
overview (page, PDF and CSV) as a row without an amount; it can be moved,
copied, duplicated, split and carried into templates like any line. It is
left out of packing list and delivery note, availability and shortages,
takeovers, after-calculation, the item lines of the XRechnung and DATEV,
sums, tax and group shares; "optional", "alternative" and discount for
several lines skip it. Whether a line is a text line can only be decided at
creation (API: `"is_text": true`). A text line can be neither "alternative
to" nor the target of a percentage surcharge.

#### Warnings and links in the planning

In the planning:

- **Discount above the maximum:** If you type a higher discount than the
  line (group, personnel, vehicle) allows, your entry stays, the maximum is
  billed, and a warning says so: "20 % will be applied". In the dialog the
  hint shows under the field already; the API returns `warnings` with a 2xx
  status. The overall discount (below) has no maximum; duplicates and group
  copies do not warn.
- **End of the event:** If the event ends after "Material zurück bis" (material
  back by), the project form warns while you type and after saving ("The
  event ends after "Material zurück bis". Check the period."), likewise when
  moving in the calendar or timeline, and the API (`warnings`). Nothing is
  prevented; service cases do not have the warning.
- **Product number as a link:** In the planning (and in the title of the line
  dialog) the number leads to the product – with the right to read
  products. Its "Availability" box is preset to the project's rental
  period, with the note "Period of the project 2027-0001 · Back to …"; a
  period you type wins over the suggestion.
- **Same look of the input rows:** Material, Personnel and Logistics have the
  same row – fields 40 px high in one line, help texts below, buttons as a
  group, below 720 px stacked.

#### Importing an MVR file

The lighting designer sends their plot from Vectorworks, grandMA3, Capture
or WYSIWYG as an **MVR file**? Then you do not have to count the spotlights.
**"Import light plot (MVR)"** below the groups:

1. Choose the MVR file, **"Read the file"**. Rentalars counts the fixtures
   per fixture type and mode – spotlights, but also trusses, screens and
   projectors, including in nested groups of the plot.
2. Under **"Assign products to the fixture types"** you see, for each type,
   the counted quantity and a suggested product. **"remembered"** means:
   someone has chosen this product for the same type before (**"remembered
   for another mode"**: for the same type in another mode); **"similar"**
   means: the name matches. You can change any suggestion, search for a
   different one under **"another product:"**, or leave the type out with
   **"do not take over"**. Rentalars never suggests services, incidental
   costs, surcharges, subrentals or vehicles.
3. Under **"Where the lines go"** choose an existing group, "without
   group" or **"a new group"** with a name.
4. **"Add the lines"** creates one line per type with the counted quantity
   – with price, discount and traffic light as if added by hand. All or
   nothing: if one line fails, none is created.

Rentalars remembers your mapping for the next plot.

**The file stays with the project.** While reading it, Rentalars already
files the MVR file in the files of the project (tab "Documents", section
11, "Files of the project"). Its name begins with date and time, such as
`20261013-221530_Rig.mvr` – so the plots of a project appear in the order
they came in. The file has no document type and is not visible to the
crew; both can be changed with the pencil of the file. "Choose another
file" removes it again. If the file is larger than project files may be,
Rentalars does not file it and says so; you can still take over the lines.
You can also upload an MVR file to the files by hand.

### Schedule: open items, timeline, phases, personnel

The tab **Schedule** gathers what everyone
working on the project needs to know – from top to bottom the open items,
the timeline of the project, the phases with their personnel and finally
the trips:

- **Open items:** what is still missing. Type in one item per line,
  "Note". Tick it off with the check box in front of it; Rentalars
  remembers who did it and when. Noted by mistake? Bin.
- **Timeline:** the project as a timeline, as under "Planning" → "Timeline"
  (section 15). At the top the **rental period** in the colour of the status
  and, if entered, the **event**; below them each **phase** in a row of its
  own, with its times in the bar; then the **personnel** – one row per
  person with their deployments, the job function in the bar. You see the personnel as in the personnel plan (section 15, "Personnel
  plan"): firm, option and inquiry in their colours, requested deployments
  dashed; declined: hatched red and struck through. Open places are shown
  hatched yellow per job function with "open". If someone is planned twice –
  also in another project –, absent or "not available", the deployment is
  **filled red**, and there is a "!" in front of the name. If you may view
  the personnel, each person's availability is shown, hatched, above their
  deployments. If you move the mouse over a bar, it gives the exact times,
  person, job function and state of the request; the legend below is that of
  the personnel plan. Those who may see the personnel get to the person via
  the name. The timeline opens with the rental period – up to 10 days in
  hour columns, longer projects in weeks (at most twelve). "Days", "Weeks",
  "‹ earlier", "later ›" and "From" work as in the planning, and scrolling
  sideways to the edge loads the next hours; unlike there, Rentalars does
  not remember your choice – the next time you open it, it shows the rental
  period again. If a phase or a deployment lies outside the days shown, the
  row stays, without a bar. In the hour columns you drag the rental period,
  event and phases – also the deployments of the people and the
  open places – to another time, or make them longer or shorter at one
  end; a click on their bar opens a window in which you type the times
  (section 15, "Moving appointments in the timeline"). If a person is the
  only one of their phase, the phase goes along (below, "Dragging people
  in the timeline").
- **Phases:** **Planning and meetings**, **Packing**, Travel, Setup,
  Rehearsal, Event, Teardown, Return, **Follow-up work**, Cleaning and
  finally Other – this is the order in which they appear in the selection;
  each with period and place, if you like with a title of its own
  ("Aufbau Halle 3", "Showtag 2"). The phases also appear in the
  overview for the crew, in the calendar and in the timeline. This is how
  you map an event over several days or in several parts: one phase per
  part.

  **What a new phase starts with**. "New phase" and the
  dialog "New phase …" suggest: the period you have already entered in the
  form of the personnel or of a vehicle, if it differs from the rental
  period; otherwise the continuation of the latest phase so far – the new
  one begins where that one ends, as long as this lies within the rental
  period, else at the start of the rental period. The new phase at first
  lasts **at most eight hours**: from the start of the rental period or where the
  latest phase ends, never beyond the end – if the project is shorter, it
  ends with it. This is only the suggestion; you make it longer by hand in
  the page, the dialog or the API. A period you type yourself over several
  days still starts with **one hour on the first day**; usually you then
  only change the times. A phase over several days
  you set up on purpose, with the day of its end. In older phases, whoever had changed only the times got a
  phase up to the last day ("Anfahrt Mon 08:15 – Tue 09:00") – vehicles on
  it were booked twice and trailers charged for two days. You correct such
  phases in the schedule, with the box "Move the crew and the vehicles of
  this phase along" ticked – then the bookings follow.
  - **"Planning and meetings"** is for site visits and technical meetings,
    even weeks before the rental period.
  - **"Packing"** – putting material together and loading it. The loading date of a packing list is called
    "Loading" (section 10).
  - **"Follow-up work"** is the time after the return: unpacking material
    from transport, incoming inspection, putting it away.

  In the form of a phase – "New phase", editing and the dialog "New phase
  …" – the rental period (grey) and the event (green) are hatched in the
  calendars; the legend below gives the times (section 2, "Entering
  periods").

  **Creating personnel places along with it**. "New phase"
  and the dialog "New phase …" have the box **"Personnel places
  (optional)"**: per row a **job function** and the number of **places**,
  "Another job function" for one more row, the bin for one less – for
  example "Stagehand, 4" and "Lighting technician, 1". Saving the phase
  creates that many **open places** in it, with its period; you fill in
  the people afterwards with "Personnel for this phase" (below). If you
  create the phase in the dialog from the planning, its personnel shows
  there at once.

  A phase **outside the rental period** – the site visit three weeks
  before – appears in the calendar and in the timeline on its day, in the
  timeline in the row of its project. It does not take up material; only
  the rental period counts for that. That is why **Rentalars asks** when
  you save a phase that lies wholly or partly outside the rental period
  (below, "Phase outside the rental period") – never for "Planning and
  meetings", though.
- **Personnel per phase:** below each phase is who works there – job
  function, person or "open", the hours and, if it differs from the period
  of the phase, its own period. With **"Personnel for this phase"** you plan
  directly for the phase, job function by job function – as
  "New items" asks for a serial number per piece:

  1. **"1. Job functions and places":** per row a job function and the
     number of its places; "Another job function" adds a row (at most ten),
     the bin removes one. The open places the phase already has are filled
     in here.
  2. **"2. People":** one field per place, **"Place 1"**, "Place 2" …; it
     suggests the people with this job function and says whether someone
     is already planned elsewhere, absent or "not available" at the time of
     the phase. An empty place stays open.

  **"Plan"** plans everybody for the period of the phase. A person chosen
  fills an open place of their job function in the phase first – so
  nothing is planned twice –; places beyond them are added. With
  **"Planned firmly (without request)"** the people chosen are planned
  without a request (section 12, "Requests: acceptance or refusal").
  Without JavaScript it takes two steps: after the job functions, "On to
  the people".

  Personnel that belongs to no
  phase is listed below under **"Personnel without phase"**; "To the
  planning" leads to its block in the planning (section 12, "Planning
  personnel in a project"). If you plan personnel there and the phase is
  still missing, you create it right away with **"New phase …"** in the
  phase selection, without switching to the schedule.

  **Changing the personnel of a phase.** If you may plan personnel, each
  row has the pencil: it opens the personnel dialog of the planning. There
  you fill an open place with a person ("Fill with a person") or change
  the person, job function or times. Rentalars names on the row and after
  saving what does not fit – overlap, absence, availability. With
  **"ask"** you send the person a request, with "enter: accepted" or
  "declined" you enter their answer, with the bin you remove the line.
  Afterwards the schedule is shown again, in its new state.
- **Trips:** every trip of the project that Rentalars works out from the
  phases and addresses, and your own trips, with time, route, the vehicles
  of the logistics on them (below, "Logistics") and the link **"Route in
  Google Maps"** – from your location via the stops to the destination
  (below, "The trips of a project").

The schedule has no box **"Venue"** of its own.
The venue is shown in the head of the project – those who may see
customers get via its name to its page with address, access, power and
site plan/hall plan –, and with all its notes in the tab "Overview", which
the crew sees too (section 12).

**Phase outside the rental period.** If a phase lies wholly or partly
outside the rental period, it is saved anyway. Rentalars then asks – on the
schedule or, with the dialog "New phase …", in the dialog itself –: "Extend
the rental period to Fri 23/10 14:00 – Tue 27/10 18:00?" The suggestion
is the previous rental period, extended just far enough to cover the
phase.

- **"Extend"** changes the rental period like "Edit project": lines with
  the previous rental period take over the new one, everyone planned in the
  project is notified, and if material is missing as a result, Rentalars
  says so ("With the new rental period 2 pieces are missing. See the lines
  marked in red.").
- **"Do not extend"** leaves everything as it is. The phase stays saved;
  material is still only reserved for the rental period.

Phases of the kind **"Planning and meetings"** never ask – a site visit
weeks before should not block any material. For a **subproject** the new
rental period has to lie within the whole project; otherwise Rentalars
names the rental period of the whole project and does not offer
"Extend" – in that case extend its rental period first.

**Moving a phase.** If personnel belongs to a phase, the form of the phase
has **"Move the crew of this phase along"** (ticked) – if vehicle bookings
belong to it as well, **"Move the crew and the vehicles of this phase
along"**; the bookings move by the same rule as the crew. If its period
changes, a crew line with exactly the period of the phase gets the new
one; every other one moves as far as the start of the phase and keeps its
length. So if only the end of the phase changes, they stay where they are.
Suggested hours move along, typed-in hours, days and rates stay. Rentalars
says how many crew lines have moved along, and whether someone is already
planned elsewhere or not available at the new time. Anyone who had been
asked or had accepted for the old times automatically gets a new request
with the new times (section 12, "Requests: acceptance or refusal"). If you
remove a phase, its personnel is kept with its period – just without a
phase. Moving is quicker in the timeline above: drag the bar of the phase,
look at the consequences in the window, "Move" (section 15, "Moving appointments
in the timeline").

**Dragging people in the timeline**. In the timeline of the
schedule you also drag the deployment of a person or an open place – with
the mouse or the arrow keys, with the same window and the same right as
for phases. What goes along follows a narrow rule:

- **If the person is the only one of their phase** (open places do not
  count), the **phase** goes along – with its open places and vehicle
  bookings. If the deployment has exactly the times of the phase, the phase
  gets the new times; otherwise it moves as far as the start of the
  deployment – if you only change its end, the phase stays. If the phase
  then lies outside the rental period, the window asks, as when dragging a
  phase, whether to extend the rental period.
- **Otherwise** the **open places of their job function** in the same phase
  (or, without a phase, among the personnel without phase) that have
  exactly the same times go along – if no other person of this job
  function has the same times.
- Otherwise only this deployment moves; likewise when you drag an open
  place.

The window says what goes along and why ("The phase “Setup” moves along
because Anna Becker is the only person in it."), with the ticked box
**"Move the phase “Setup” along"** or **"Move the open places as Stagehand
along"** – without the tick only this deployment moves. Below it is who is
asked again and which overlaps there are; every person affected gets one
message (section 12, "Messages about the deployment"). In the personnel
plan under Planning you still move only the single deployment (section
15, "Personnel plan").

**The trips of a project.** At the bottom of the schedule – and in the
overview for the drivers – the trips that Rentalars works out from the
phases and addresses are listed under **"Trips"**:

| Trip | When | Route |
|---|---|---|
| To the setup, Back from the setup | start and end of each phase "Setup" | warehouse → venue, and back |
| To the teardown, Back from the teardown | start and end of each phase "Teardown" | likewise |
| Pickup at the suppliers | start of the phase "Packing" | warehouse → each supplier where things are picked up → warehouse |
| Return to the suppliers | start of the phase "Follow-up work" | likewise |

Things are only picked up and brought back for subrentals where **"Picked
up at the supplier"** is ticked (section 9, "Subrenting"); without a phase
"Packing" or "Follow-up work", the start and end of the subrental count.
Optional and alternative lines are left out. The venue is that of the
phase, otherwise that of the project, otherwise the typed-in place of the
phase or of the project, otherwise the delivery address. The warehouse is
the "address of the warehouse" under "Settings" → "Company data and
settings" – if empty, the address of the company.

Every trip has the link **"Route in Google Maps"**; it opens the route
planner in a new tab, starts at your current location and leads via the
stops of the trip to the destination. The schedule still shows the start of
the trip (for instance the warehouse), but the link begins where you are
right now. Rentalars does not calculate driving times, and distances only
with the route service, as a suggestion for the kilometres of a vehicle
(below, "Logistics"). If an address is missing, the schedule says on the trip which one ("The supplier …
has no address yet."); the overview leaves such hints out. Below that,
"Show map" shows all places of the trips on a map (section 6, "Route and
map"). If there is no trip yet, it says there what trips come from.

**Adjusting trips.** Anyone who may edit the project adjusts a trip with
the pencil ("Change trip"): departure, start, stops (one address per line,
at most nine), destination, title and a note that the drivers see in the
overview. Whatever you leave as it is keeps following the phases. An
adjusted trip carries the label "changed"; **"Reset"** brings back the
worked-out trip. With the bin you remove a trip; it stays removed even if
the phases change, and is listed under **"Removed trips"** with "Bring
back". With **"Add trip"** you create a trip of your own, such as a later
delivery; it carries the label "own trip". The route link follows your
changes. In a closed project, trips can no longer be changed. When a
project is duplicated or divided, adjusted trips do not go along.

**"Confirmed – details open".** For the frequent case where the order is
in, but the setup times or the contact are still missing: if you set this
status, Rentalars takes you to the schedule so that you note down what is
open. From then on the material is firmly reserved. Once all items are
ticked off, **Set to "Confirmed"** appears at the top – one click is
enough.

**"Projects" → "Open items"** shows all projects with open items. Besides
the noted items, the unresolved **shortages** of the project are listed
there as further items, for instance "Shortage: 4 × LED-Scheinwerfer (2
subrented, 2 open)". A click on one opens the planning of the project at
the line concerned; it is highlighted in colour there. Projects with
shortages also appear if they have no open items. You only see projects
whose planning you may see, and the shortages only with the special right
"See availability of material"; with the project access "overview without
planning" (role Crew) the tab is not there at all.

### Logistics: vehicles and trailers

The planning has the block **"Logistics"** below the
personnel: the vehicles (motor vehicles) and trailers of your fleet that
the project needs, and which trips they drive. Vehicles are not material
lines – they are in no group, not on the packing list and do not count
towards the availability of material. Where they come from is described in
section 4, "Fleet"; their rates are on their product (section 5, "Product
kinds"). If there is no vehicle product yet, the block says so: "The fleet
is empty: …".

**Booking a vehicle.** Below the block you choose under **"Vehicle or
trailer"** a particular vehicle – grouped by product, with its licence
plate – or, under the product, **"still open, or from a supplier"** if it
is not yet clear which one goes. If the project has phases, you choose the
**"Phase"** if you like; **"From"** and **"Until"** then take its period,
otherwise the project's – or you enter one of your own. **"Book"**. An open
booking carries the badge "vehicle still open"; you choose the vehicle
later with the pencil.

**Editing a booking** – the pencil opens the dialog:

- **"Vehicle or trailer"**, **"Title"**, **"Phase"**, **"From"** and
  **"Until"**, **"Note"**;
- with the price right the **rates** – copied from the product when
  booking and the booking's own from then on; a later change of the
  product does not change them: for a motor vehicle **"Price per kilometre
  (net)"** and **"Trailer surcharge per kilometre (net)"**, for a trailer
  the **"Billing"** "per day" or "per kilometre" with **"Price per day
  (net)"**, **"Rental days"** and **"Only days with trips"** or the price
  per kilometre; also **"Discount in percent"** – at most the maximum
  discount of the product – and the **"Tax rate"**;
- with the right for purchase prices **"Internal cost per kilometre"** and
  for a trailer **"Internal cost per day"**;
- **"From the supplier"**: a vehicle you rent from a supplier you book like
  one of your own, only without a vehicle and with the supplier. What the
  supplier charges for the whole booking goes under **"What the supplier
  charges"** – that is the cost instead of the costs per kilometre and day;
  the customer pays the rates of the product as for an own vehicle.

"Save booking". The bin removes the booking with its trips.

**The trips.** Below the bookings, under **"Trips"**, are the trips of the
project: those of the phases setup and teardown, pickup and return at
suppliers and your own (above, "The trips of a project"). As soon as a
motor vehicle is booked, **"Vehicle"** (with the plus) at a trip opens the
dialog "Put a vehicle on the trip":

- **"Vehicle"** – a motor vehicle of the project – and, if you like, the
  **"Trailer"** it pulls. Several motor vehicles can drive a trip, each
  with at most one trailer.
- **"Planned km"** and **"Driven km"**. If your administrator has set up
  the route service, **"Suggest planned km from the route"** suggests the
  kilometres over all stops of the trip – "… km by the route – a
  suggestion you can change." If a place has no address or the service
  finds no route, the message names the place ("“Warehouse” has no address
  yet."). Without a route service there is no button, and you enter the
  kilometres by hand (section 16, "Company data and settings").
- with the price right **"Charged"**: "driven kilometres" (preset – until
  they are entered, the planned ones stand in, with the badge "estimate"),
  "planned kilometres" or "flat rate for the trip" with its amount –
  vehicle, surcharge and a trailer billed per kilometre together;
- **"Note"**.

Each vehicle on a trip has "Change" and "Take off". If a trip is gone – its
phase was removed or the trip deleted –, its vehicles stand with their
kilometres under "A trip that is gone" and are **not charged**; put them on
another trip or remove them.

**What is charged:**

| Booking | Amount |
|---|---|
| motor vehicle | per trip the kilometres × price per kilometre; if it pulls a trailer on that trip, automatically × (price per kilometre + trailer surcharge) – or the trip's flat rate |
| trailer per kilometre | per trip the same kilometres as its motor vehicle × its price per kilometre; with a flat rate it is included in it |
| trailer per day | price per day × the factor of the rental scale for its days, as for material (section 8); without a scale every day counts in full. Days: entered on the booking, else those of its own period, else the project's rental days – with "Only days with trips" only the days on which it drives |

The column "Charged" shows the kilometres and the number of trips or the
days, "Price" the rate, e.g. "+ €0.20 per km with a trailer", "Amount" the
result with "of which trailer surcharge …". The column **"Costs"** (with
the right for purchase prices): the kilometres of each trip – driven, else
planned – × internal cost per kilometre, for a trailer per day its days ×
internal cost per day; a vehicle from a supplier costs what the supplier
charges. Below is the "Subtotal logistics".

**Warnings.** Rentalars points things out on the booking and after saving,
but prevents nothing:

- the vehicle is **booked elsewhere** at the same time ("Also booked for
  project 2027-0042 from … to …" – with the number only, as not everybody
  may open the other project) or twice in this project;
- it is **not fit for use** – defective, under repair, blocked – or has a
  **blocked period**;
- an **inspection** such as HU or UVV is overdue or due before the booking
  ends;
- more people travel with it than it has **seats**;
- the driver has **no driving licence of the class** the vehicle or the
  combination needs – checked only if your qualification types name
  driving licence classes (section 12, "Qualifications and
  certificates");
- the motor vehicle **may not tow a trailer**, or the trailer weighs more
  than it may tow.

**Who travels with it.** In the dialog of a crew line you choose a motor
vehicle of the project under **"Vehicle"** and tick **"Drives the
vehicle"** if the person drives (section 12, "Planning personnel in a
project"). The booking then shows "With it: …", the driver with "driver".
The vehicle is also named on the crew line, in the person's overview, in
the crew disposition and under My area → "My deployments". The driving
time is working time of the crew line; the logistics only charges the
vehicle.

**The logistics follows the project.** Bookings with the project's period
take a new one; bookings of a phase move with it (above, "Moving a
phase"), and moving the whole project in the timeline takes them along
(section 15). How duplicating, templates and subprojects deal with the
logistics is described in the sections below.

**Totals and documents.** The logistics is part of the net total, the
tax, the basis of a surcharge on the whole project and the profit from the
project (section 8). Offer, order confirmation and invoice have a section
"Logistics" (section 11); the packing list names the vehicle it is loaded
into (section 10, "The packing list").

**Who may.** Whoever may edit the project may book vehicles and put them
on trips – or whoever may read it and edit material, as the fleet belongs
to the material. Rates, billing and discounts only those who may see
prices, costs only those who may see purchase prices. In a closed project
the logistics can no longer be changed; a service case has none.

### Duplicating a project

The town festival every year, the trade fair every autumn: **"Duplicate"**
at the top of the project page turns a project into a new one, for a new
period.

- Taken over are customer, contact, venue, notes and the **phases**, moved
  into the new period.
- **Material** if you like (preset), with groups, prices and discounts.
  Lines with a period of their own keep their position relative to the
  start; times stay the same even across a change of clocks.
- **Personnel** if you like – as open places, each in its phase. Who has
  time on the new dates is a new question.
- **Logistics** if you like (**"with the logistics (vehicles
  and their trips)"**): the vehicle bookings with vehicle, rates and phase,
  moved like the lines, and the vehicles on the trips to setup and
  teardown, pickup and return – with trailer, planned kilometres and what
  is charged, but without driven kilometres. Your own trips are not
  copied. If a vehicle is already booked on the new dates, the copy's
  logistics says so. If the personnel is copied as well, it keeps its
  vehicle.
- In the copy, alternatives name the copied line or group they are an
  alternative to.
- Subrentals start in the copy with the status **"open"** – nothing has
  been requested from the supplier for them yet (section 9, "Subrenting").
  Older material lines with a service are
  left out of the copy; plan the personnel in the block Personnel.
- The copy starts as an **inquiry**, with you as project manager.

**A whole project** is copied with its subprojects – **"with the
subprojects"** is preset (below, "Subprojects"):

- Each subproject keeps its position relative to the start and its
  duration. If the new period is shorter, it is shortened to fit.
- Whatever a subproject has set differently itself – project manager,
  delivery address, contact, venue – it keeps.
- Takeovers between the subprojects are kept. If one no longer fits, it
  becomes a normal line; the page says how many.
- Subprojects cancelled individually are not copied.

**Duplicating a subproject:** with the tick box **"as a new subproject of
the same whole project"** (preset) the copy becomes another subproject; its
period must lie within the period of the whole project, and it starts with
the status a new subproject gets there – for a confirmed whole project
"Confirmed – details open". For this you need to be allowed to edit the
whole project. Without the tick, the copy becomes a project of its own, and
taken-over lines become normal lines.

### Project templates

Duplicating takes a project along with its customer and prices. For
formats that keep coming back with different customers – the "Standard"
wedding, the company party with a small stage – there are **templates**:
the structure of a proven project, without customer and without old
prices.

**Saving a template.** **"Save as template"** at the top of the project
page opens a dialog:

- **"Name of the template"** – prefilled with the name of the project – and
  a **"Description"**;
- what comes along: **"Groups and material"**, **"Crew places and vehicle
  bookings (open, without people and vehicles)"**, **"Schedule: phases and open items"** – all of it by
  default;
- **"Replace a template of the same name"**, if there already is a template
  of that name and the new one is to replace it. Without the tick,
  Rentalars refuses a duplicate name.

"Save template". A template captures **one** project: from a whole project
it only contains its own lines; you save subprojects as templates one by
one – the dialog says so. What the template keeps:

- the **groups** with their settings and their nesting, and the **lines**
  with product, quantity, rental or sale, note, wished-for model and
  "Counts as" – an alternative with the line or group it could replace;
  lines without product with title and price (an older material line with
  a service is left out by Rentalars when the template is applied, and it
  says so, below);
- the **crew lines** with job function, hours, phase, meeting point and
  note – without people, so as open places;
- with them, the **vehicle bookings** with product, title,
  note, phase and period – as open bookings of their product, without the
  vehicle itself and with the rates the product has on the day of the new
  project;
- the **phases** and **open items** and the notes of the project.

It remembers all times **relative to the start** of the project: the setup
"the day before at 14:00" is again the day before at 14:00 in the new
project. A line with a period of its own keeps its
position relative to the start, shortened to the new rental period.

What it does **not** keep: customer, venue, status, people and the prices
of the products. A template is often used months later; then the **prices
of the day** on which the new project is created apply, and the standard
discount of the new customer – as if you were adding the lines by hand.
Only the discount and flat price of a group and the price of lines without
product are kept, and only if whoever saves the template may see prices.

**Starting a project with a template.** "Projects" → "New project", choose
the template in the field **"Template"**, name, customer and period as
always. When you save, groups, lines, crew lines, vehicle bookings and the
schedule are added, with the availability of the new period. If a product or a job function
has been deactivated or deleted in the meantime, Rentalars leaves that
line out and says so ("Left out from the template: …") – likewise a
material line with a service ("a service, planned under Personnel: …").

**Editing the content of a template.** A click on the name in the list
of templates (or "Edit content" on the page of the template) opens the **content**: as a
new project gets it from the template – groups with their lines, crew places, vehicle
bookings, phases, open items and the notes. An entry can be **added** ("Add product",
"Add free line", "Add text", "Add group", "Add crew place" …), **changed**, **moved one
place up or down** with the arrows and **deleted**. A group you delete asks first what
happens to its content: take its place in the group above, or be deleted with it. Periods
are given in **hours from the start** of the project ("From (hours)", "Until (hours)"),
if wished from its **end** ("return three hours before the end"); "Phase" names the phase a
place or booking belongs to. Rentalars checks every change for consistency – a line in a
group that exists, an alternative that replaces something that exists, the nesting of the
groups – and stores nothing that creating a project could not read. **Prices** (discount
and flat price of a group, price of a free line) are seen and changed only by whoever may
see prices; for everybody else they stay as they are. If somebody else has changed or
deleted an entry in the meantime, the page says so ("This entry was changed or removed by
somebody else") instead of hitting the wrong entry. **Projects that were made from the
template already do not change.** This needs the right to edit projects. The API does the
same (`/project-templates/{id}/content`).

**Managing templates.** "Projects" → **"Templates"** lists all templates
with their content ("3 groups, 42 lines, 4 crew places, 5 phases"), the
project they came from, and who created them when. A click on the name
opens the content (see above); name and description are changed on the page "Edit
template"; "delete" removes it (with the right
to delete projects). Projects created from a template stay as they are.

**The supplied template "Dry Hire (rental without crew)".** New
installations get it during the initial setup, existing ones with an
update – only if there was no template of that name yet. It
contains no lines and no personnel, but four phases instead, each with the
place "Warehouse" and a short note, and a project note saying that
the customer picks up and brings back:

| Phase | When |
|---|---|
| Packing | the first two hours of the rental period |
| Handover to the customer (collection) – kind "Other" | the hour after that |
| Return – kind "Return" | three to two hours before the end |
| Follow-up work | the last two hours |

Unlike templates you save yourself, the return and follow-up work are
based on the **end** of the rental period; that way they fit any rental
duration. If the rental period is very short, they are shortened to fit.
You can rename the template, replace it with one of your own of the same
name, or delete it; once deleted, it does not come back. If you save a
project created from it as a template of your own, that template again
remembers all times relative to the start.

### Dry hire – rental without personnel

The customer picks the material up at the warehouse, sets it up
themselves and brings it back – without your personnel and without
transport. This is how you handle it:

1. **"Projects" → "New project"**, under "Template" choose **"Dry Hire
   (rental without crew)"**, enter name and customer.
2. **Rental period:** from packing before the pickup until after the
   return – for that long the material is taken for other projects. Pickup
   on Friday at 14:00, return on Monday at 09:00: Friday 12:00 to Monday
   12:00. Then packing (12:00 to 14:00) and handover (14:00 to 15:00) fall on
   Friday, the return (09:00 to 10:00) and follow-up work (10:00 to 12:00) on
   Monday. If the customer comes at a different time, you change the times
   of the phases in the schedule.
3. You enter the **rental days** the way you charge them – for instance one
   day for a weekend, if that is how you do it; if empty, Rentalars works
   them out from the rental period (above, "Creating a project").
4. Add **material** as usual; availability, traffic light and prices work
   as in any project.
5. **Documents:** offer and order confirmation as always. At the pickup,
   **pack and hand out** (section 10) and then make the **delivery note** –
   it lists the items handed out and has the fields for the customer's
   signature. When the material comes back, tick off the **return** on the
   packing list and book it with "Book the return" – once everything is back,
   the project goes to "Returned" on its own – and make the **invoice**.

Personnel and transport are simply missing; if you do need someone after
all, for instance for a briefing, you plan them in as in any project.
Without a venue and without a delivery address of its own, the delivery
note shows the customer's address – exactly right for a pickup. If you
often rent out the same package without personnel, save such a project as
a template of your own.

### History

The tab "History" shows every change to the project: who changed the
status when, added a line or a vehicle, changed a quantity or a price, created a phase,
file or open item, assigned a mail to another project or to a subrental,
made, cancelled, sent or handed over a document to Lexware Office, handed
material over to another subproject, set or completed a follow-up, divided
the project into subprojects, moved a date in the timeline or corrected a
position on the map. Price changes are only seen by those who may see
prices. The subject of a mail or the title of a note of the
correspondence is seen only by those who may read that message (section
14, "Messages with a lock"); the others see an entry without the subject,
such as "Message received on …" or "Note of …". Messages in the chat are
not in the history but in the chat.

### Chat in the project

Quick arrangements within the team – "Bühne steht, Licht kommt um 15 Uhr",
"Wer bringt die Kabeltrommel mit?" – do not belong in the correspondence
with the customer. For this, every project, every subproject and every
service case has the tab **"Chat"**.

- **Who reads along:** everyone who can open the project – including the
  crew planned in, who otherwise only see the overview. The page says so
  at the top, and **"… people read along"** unfolds to show who. So do not
  write anything in it that the crew should not read, such as prices.
- **Writing:** text in the field "Message", **"Send"** – or
  **Ctrl+Enter**. Every message is shown with name and time, the newest at
  the bottom; **"Older messages"** fetches earlier ones.
- **Photos and videos**: below the field you choose files with
  **"Attach photos or videos"**; on a phone **"Take a photo or video"**
  opens the camera straight away. A message may consist of photos and
  videos only, without text. Allowed are up to **10 files** per message,
  **photos up to 25 MB**, **videos up to 200 MB and 20 minutes**, together
  up to 500 MB; the content of the file is checked, not its extension. A
  photo in PNG, GIF or WebP may have at most **16 megapixels**; the server
  refuses a larger one ("Please send larger photos as JPEG.") – as a JPEG
  it may have up to 150 megapixels. Also refused are videos whose picture
  has more than 4096 pixels on one side, with more than 240 frames per
  second or with more frames than 20 minutes at 60 frames per second.
  **The server makes everything smaller and keeps only the small
  version** – the original is gone afterwards: photos are turned upright,
  reduced to at most 2048 pixels on the long side and stored **with the
  place of the shot (GPS) as the only detail**, without device and time of the camera;
  the chat shows a preview, a click opens the photo in full size. Videos
  are made smaller by the server in the background to at most 720p (MP4),
  one after the other – until then it says **"Video is being made
  smaller …"**. If several people send videos at the same time, yours
  waits until the ones before it are done, and the note stays
  correspondingly longer. If making it smaller fails, the video is
  discarded, the message says so, and whoever sent it gets a
  notification. If the server lacks the program for it, the form says
  "Videos are not possible at the moment: the server lacks ffmpeg." –
  photos work all the same. The photos and videos are seen by whoever may
  read the chat; if the message is deleted, they go with it.
- **Mentioning someone:** type **@** and the beginning of a name, then
  choose from the list (arrow keys and Enter, or a click) – or click a name
  in "… people read along". The person gets a notification "… mentioned you
  in the chat of …", in Rentalars and – as set under "My account" →
  "Notifications", on by default – by mail. You can only mention someone
  who can read the chat.
- **Changing and deleting:** your own messages in the first **15 minutes**
  after writing them; a changed message carries "changed" afterwards.
  Anyone newly mentioned in a changed message is notified, the others not
  again. **If you delete a message**, Rentalars also deletes the AI summaries
  of the project (and their earlier versions) that read the chat after that
  message – otherwise its content would still stand there (section 14,
  "Summary and short overview"). You write a new summary with "Summarise".
- **New messages** from others appear on their own, without the page
  reloading – what you are typing stays put. On the other tabs of the
  project, "Chat" shows the number of messages you have not read yet.

You can write in every status, even in a closed project.

### Subprojects

A large production – a town festival with several stages, for instance –
is planned as a **whole project** with **subprojects**. Each subproject is
a project in its own right: with its own name, venue, project manager,
rental period and rental days – a stage may have to be ready a day earlier
–, its own lines with groups, its own personnel and its own status.
Shared things – central power supply, production management – you plan
directly on the whole project. There is exactly one level: a subproject
has no subprojects.

#### Creating a subproject

**"Add subproject"** at the top of the page of the whole project opens the
form "New subproject":

- You give it its **name** – "Bühne Marktplatz". **Venue, project manager,
  contact, delivery address and rental period** are suggested from the
  whole project and can be changed. Like any new project, a subproject can
  also start with a **template** (above, "Project templates").
- **Customer and billing address** are always those of the whole project;
  the form only displays them ("From the whole project, with its billing
  address. Change them there."). If the customer or the billing address
  changes on the whole project, they change in all subprojects.
- The **rental period** lies within the rental period of the whole
  project. If you move that of the whole project as a whole – start and end
  by the same amount of time –, the subprojects move along. If you shorten
  it so that a subproject would stick out, Rentalars refuses; in that case
  change the subproject first.

The subproject gets the **number** of the whole project with a counter:
`2026-0042-1`, `2026-0042-2`. It can be reached under this number, and
`[RL#2026-0042-1]` is its code for mails (section 14). Above the name it
says "subproject", and the line above that leads to the whole project.

A new subproject starts with the status that fits its whole project: for
an inquiry as an inquiry, for an option as an option, for a confirmed
whole project as **"Confirmed – details open"** – a new stage is rarely
fully planned straight away. A cancelled or closed whole project gets no
new subprojects.

#### Dividing a project afterwards

The town festival was planned as one project, with one group per stage –
and now each stage is to get its own period, its packing list and its status?
Then nothing has to be created anew: in the head of the project, at the
arrow ▾ next to "Add subproject", there is **"Divide into subprojects"**.

1. Under **"Groups that become subprojects"** you choose the groups of the
   top level that are to become subprojects of their own. Next to each it
   says how many lines and subgroups it has and what becomes of it.
2. Under **"Crew"** you choose for each crew line under "Goes to" where it
   goes: it "stays at the whole project" or "goes with "…"" one of the
   chosen groups – personnel is not in any group, which is why Rentalars
   asks. Its time entries go along, its phase is copied into the
   subproject.
3. **"Divide into subprojects".**

The project becomes the **whole project**. Each chosen group becomes a
subproject with the number of the project and "-1", "-2" …, with its
lines, with the rental period, the event, the rental days and the status of
the project and the presets of a new subproject (venue, contact, project
manager). The group itself is dissolved in the process: its lines are in
the subproject without a group, its subgroups become its groups. If it has
a discount, a flat price, rental days of its own, a description, is
optional or an alternative, or if a surcharge refers to it, it stays as a
group in the subproject – that way the prices stay the same. A subrental
that covers a shortage goes with its line.

What you do not choose stays at the whole project – central power supply,
production office. Documents, mails, files, phases, open items, the
follow-up and the logistics also stay at the whole project; a crew line
that goes to a subproject no longer names a vehicle afterwards. Afterwards each subproject can
get its own period, venue, a packing list and a status.

It is **not possible** in a subproject and for a service case, when the
project is out, returned, closed or cancelled, for a group whose material
has already been packed or handed out, and when an alternative or a
surcharge reaches across the new boundary – the page gives the reason for
each group. If a percentage surcharge refers to the whole project,
Rentalars tells you beforehand: it stays at the whole project and from then
on only applies to what stays there. If the project has no groups yet,
first put the lines of each future part together in a group.

**Split periods stay together**. If someone has split a
period across several job functions (section 13, "Several job functions in
one period"), the parts belong to different crew lines. If these lines went
into different subprojects, the period would be torn apart – which is why
Rentalars then refuses the division and names the person, day, times and
job functions. Choose the same target for these crew lines; if they go
together, the whole period goes along.

**On a whole project** the same item is called **"Turn groups into
subprojects"**: each chosen group of the whole project becomes a further
subproject with its periods; the existing subprojects stay as they are.

The history of the whole project records "Divided into subprojects: …",
and that of each new subproject which group it came from.

#### The "Subprojects" tab

On the whole project and on each subproject, the tab **"Subprojects"**
shows all parts side by side: one row for the whole project's own lines,
one per subproject, with rental period, lines, pieces, personnel, open
places, hours, net (with the price right) and shortages – and below that
the total of everything ("Whole project with all parts"). Below that are
the **"Shortages between the parts"**: lines that are short of something
because other subprojects firmly take up the same material at the same
time. Subprojects whose planning you may not read are missing; the page
says how many, and the totals are without them.

Above the planning, a **bar** leads to the whole project and to each part
– that way you switch quickly from stage to stage.

#### Status

Each subproject has its own status. If you change the status of the whole
project, the tick box **"subprojects too"** next to the list "Change
status to …" – it is ticked – takes the parts along where the step is
possible for them; the others keep their status, and Rentalars names them.
Three rules always apply:

- The whole project is always **cancelled** together with its parts; the
  confirmation question says so. If material of a subproject is out – even
  just part of it –, this is not possible.
- The whole project can only be **closed** once all parts are closed or
  cancelled.
- A subproject of a cancelled whole project cannot be taken up again on its
  own – take up the whole project again first.

A whole project with subprojects cannot be deleted.

#### Access

For those who only see assigned projects (section 12, "Who sees which
project"):

- **Members of the whole project** have the same access in all
  subprojects.
- Under **"Access" of a subproject** you give a member different access
  there – more or less – or **"no access"**. This membership replaces the
  one in the whole project, for this part only.
- A membership **only in one subproject** opens only that one – neither the
  whole project nor the other parts. An external stage manager thus gets
  exactly their stage.
- Anyone who is **planned** in a subproject sees its overview and
  packing list, even with "no access".

Anyone who sees a subproject also sees the number and name of its whole
project ("part of 2026-0042 Stadtfest"). Roles for all projects apply in
all parts, as before.

#### Material that moves on: takeover

If the same pieces are to stand first on one stage and then on the other,
plan them in the later subproject as a **takeover**:

1. In the planning of the later subproject, **"Take over from another
   subproject"**. The dialog shows the lines of the other parts (and of the
   whole project) that start earlier and still have pieces left – with
   "Left" and when they are free there.
2. Choose the line, enter the quantity (preset: everything that is left)
   and the group the takeover goes into; "Take over".

Or, in the dialog of a line, under **"Taken over from"** choose the line
the pieces come from – lines of the same product that start earlier are
offered. Goods sold cannot be taken over.

What the takeover does:

- **Availability:** the pieces count as out without a break, from the first
  subproject until the end of the second – without buffer times in
  between, since they do not go back to the warehouse. If the periods
  overlap, the planning shows a shortage: the same pieces cannot stand on
  two stages at once.
- **Price:** the line taken over costs nothing – it is charged where it
  comes from. It carries the label "taken over", "comes from …" and "not
  charged / charged in 2026-0042-1".
- **At the other end**, the line being taken over from shows "6 go on to
  …". It cannot be reduced below the quantity others take over; if you
  delete it, the lines taking over become normal ones.
- **Packing list:** the pieces are on both packing lists; their arrival is booked
  as a **handover** (section 10, "Takeover and handover between
  subprojects").

#### Calculating, packing, invoicing

- **Invoicing is done on the whole project:** offer, order confirmation and
  invoice contain all subprojects; delivery notes and crew schedules are
  made on the subproject (section 11, "Whole project and subprojects").
- The **price overview** of the whole project shows all parts and the total
  of all (section 8).
- Each subproject is **packed and handed out** on its own; above each
  packing list the other parts appear as tabs, and **"All parts together"**
  shows the packing list of the whole project with all parts (section 10).

#### Subprojects in the rest of the application

- **Duplicate:** a whole project is copied with its subprojects, a
  subproject as a new subproject of the same whole project or as a project
  of its own (above, "Duplicating a project").
- **Templates:** a template from a whole project contains only its own
  lines; you save subprojects as templates one by one.
- **Calendar, timeline, personnel plan:** subprojects are called "Bühne
  Marktplatz (Stadtfest)", the tooltip says "part of 2026-0042 Stadtfest".
  In the timeline they appear indented below their whole project. In the
  timeline of a product, material taken over starts where the line it comes
  from ends ("6× taken over").
- **Search, start page, lists:** subprojects carry "part of …". The name of
  the whole project also finds its parts. In the project list, the whole
  project shows how many subprojects it has; on the page of a customer the
  subprojects follow their whole project. On the whole project, the total
  columns of the project list show the sum of it and its subprojects
  (section 8, "Totals in the project list").
- **Shortages:** there it says "of these held by other subprojects: N"
  with a link to the tab "Subprojects" (section 9).
- **Time recording and overview:** personnel and times belong to the
  subproject. The project selection shows "2026-0042-1 Bühne Marktplatz
  (Stadtfest)"; the overview and the calendar entry name the whole project.
- **Correspondence:** mails with `[RL#2026-0042-1]` land in the
  subproject. The whole project also shows the mails of its subprojects,
  marked with their number (section 14).
- **Chat:** each subproject has its own chat (above, "Chat in the
  project").

### Service cases

A projector in a customer's conference room fails, a hotel asks for a
spare microphone, a device comes in for repair: creating a project with a
period and planning for that would be too much. A **service case** is a
quick kind of project – with number, code and correspondence, but without
material, personnel, logistics and packing list.

**"Projects" → "Service cases"** lists every case that is not done by
default ("All not done") – the waiting ones and the backlog too; you see
the done ones if you choose "Done" under "Status". You
can filter by text (number, subject, customer or who reported it), status
and "only mine". With **"New service case"** you create one:

- **"What is it about?"** – required, for instance "Beamer Saal 2 ohne
  Bild";
- **"Customer"** – required, as for a project; with the customer you choose
  one of their **contacts**. Not a customer yet? Type the name and choose
  "… as a new customer". If it is about your own material – the repair of
  a defective device, say –, tick **"Internal – our own material, no
  customer"** instead; then the case needs no customer, and
  "internal" appears for the customer;
- **"Reported by"** – name, phone or e-mail address of whoever reported it,
  if they are not a contact of the customer;
- **"Description"** (optional) and **"Responsible"** – the responsible
  person gets a notification that the case is with them.

"Create service case". The **number** comes from the number range of the
projects (`2026-0057`), and mails with the code `[RL#2026-0057]` in the
subject land in the case as in a project (section 14).

**From an inquiry.** Under "Projects" → "Inquiries", every mail without a
tag has **"As a service case"**. The form names the mail and suggests the
customer from the sender, if Rentalars knows them; when saving, Rentalars
fetches the mail from the inbox into the new case – or, if something goes
wrong, does nothing at all. This needs the right to create projects and to
edit in the module e-mail. This also works with an inquiry
somebody noted by hand – during a phone call, say (section 14,
"Inquiries"): it becomes a note in the correspondence of the case.

**Straight from a mail.** If your mailbox has an address such as
`support@` for which "create a service case at once" is set (section 14,
"Further addresses of a mailbox"), Rentalars immediately creates a service
case from every mail without a tag sent to this address – subject, customer
and contact from the sender, as far as Rentalars knows them – and notifies
the person who is "responsible for new service cases" there; they are then
"Responsible". If Rentalars does not know the sender, it creates the case
without a customer (below, "Customer missing"). If creating it fails, the
mail stays an inquiry.

**From a defect report.** Every defect reported – on the item's
page, on return or through the interface – becomes a service case by
itself: the automation "Defect report → service case" is set up and
switched on in every installation (section 16, "Automations"). The case is
called something like "Defect 0042 SM58"; the description names what is
defective, the item with its serial number, where it was found, who
reported it and when, and the link to the item. For your own material the
case is internal ("internal" and "our own material" for the customer); for
customer material it belongs to its owner. "Reported by" is whoever
reported the defect; responsible is whoever the automation names. The
photo of the report goes into the case's files. If the automation is set
up that way, the report waits under "Projects" → "Inquiries" instead
(section 14, "Inquiries"); from there – or on the "Files and defects" tab
of the item – **"As a service case"** makes the case, filled in with the
same details. One report makes at most one service case.

**"Customer missing".** Cases without a customer – from the time when the customer was optional, or created by Rentalars from the
mail of an unknown sender – stay valid and show the label "customer
missing" for the customer; whoever may edit the case sees "Choose the
customer" next to it. The next time it is edited, the form asks for the
customer; you can set the status without it, too.

**The page of a service case** has the tabs **Overview**, Documents,
Correspondence, Chat, Access and History. The first tab is
called "Overview" (before, "Service case"). It shows status, customer,
contact, "Reported by", "Responsible", when the case was created, the
description, the latest mails with "Write mail", the open items and, the box "Related" with the related projects and service cases
(above, "Related projects and service cases"). "Write
mail" appears there on the same conditions as in the Correspondence tab
(section 14, "The "Correspondence" tab"). You set
the **status** there with "Set status", in any order (below, "The status
of a service case"); "Edit service case" in the head changes the other
details. A follow-up works as for a project (above, "Follow-up"). If an
address of your mailbox has the role "only for service cases", mails you
write in the service case go out with this address as sender – it is preselected under "Sender" (section 14, "Writing and answering").
The Correspondence tab looks as in a project: above the mails is the
"Summary" box with the short overview and, if switched on, the summary by
the AI (section 14, "Summary and short overview"); you reach it through
"All … mails" or the Correspondence tab.

**The status of a service case.** Besides **"Open"**, **"In progress"**
and **"Done"**, there are three statuses that need a
follow-up:

| Status | What for | What the follow-up needs |
|---|---|---|
| **"Waiting"** – for a reply, an action or a delivery | The ball is with the customer, someone else or the supplier. The case then reads, say, "Waiting for a reply". | day (time optional) and what it waits for |
| **"Waiting to close"** | Everything is done; if nobody gets in touch before the time set, the case is closed. | day and time |
| **"Backlog"** | The case can wait. Until the follow-up it shows only under "Projects" → "Service cases". | day (time optional) |

If you choose one of them in the status list, the follow-up dialog opens
at once (with the keyboard: choose with the arrow keys, then Enter): day (for "Waiting to close" also the time), for whom, note – for
"Waiting" also what it waits for. The status is saved only together with
the follow-up; "Cancel" leaves the previous status. If you later move the
follow-up of a case that is waiting to close, the time stays required. The
statuses have colours of their own in the list and appear in the history.

- **Waiting to close:** if nothing happens before the time set, Rentalars
  closes the case ("Done") and removes the follow-up; no follow-up
  notification is sent then. If a new mail arrives or goes out, or a chat
  message is written, before that, the case is "Open" again; the follow-up
  stays as a reminder.
- **Backlog:** until the follow-up, the case is not on the start page, not
  under My area → "Service cases" and not under "Planning" → "Follow-ups"
  (there and under My area, "Also the backlog" or "also the backlog" brings
  it into the list). When the follow-up is due it is "Open" again, and the
  person gets the notification.
- **"Done" on the follow-up** of a case in one of these three statuses
  sets it back to "Open" – with a note.

Closing and reopening are done by three automations that are set up and
switched on (section 16, "Automations"); you can change them or switch
them off.

**People taking part.** On the page of a service case you add
further people under **"People taking part"**: person, if you like the
**job function** and a **note**, then "Add person". This is not crew
planning – there is no deployment request, no availability check and no
costs from the planning; the personnel plan and "Who is free?" do not know
about people taking part. The person gets the notification "Added to a
service case" (by default in Rentalars, by e-mail and in the app), sees the
case under **"My area" → "Service cases"** and on the start page under "My
service cases", and records their times on it (section 13). They work on the case whatever their role (below, "Working on the case").
If you add a person again, you only change job function and
note; deactivated people and job functions cannot be chosen. With the
**bin** ("Take off the case") you take them off the case after confirming;
their times stay. Adding and removing are recorded in the history of the
case.

**"My area" → "Service cases"** lists the cases you take part in or are
responsible for and that are not done – without the backlog until its
follow-up is due; done ones with the filter "also done ones", the backlog
with "also the backlog". It is a table like any list, and can also be
grouped by status.

**Working on the case**. Whoever is **responsible** for a
service case or **takes part** in it opens and edits it – whatever their
role, also with the role Crew and without access to the projects: status
with follow-up, the details of the case including "Responsible", the
people taking part, the open items, the chat and the correspondence of the
case – reading, writing and answering mails, writing notes; the open messages, those with a lock only with the right "See prices and
calculation" (section 14, "Messages with a lock"). The link in
the notification leads straight there, and "My area" → "Service cases"
and the start page show one's own cases even without access to the
projects. Not included are "Turn into a project", deleting, prices (they
still depend on the price right) and every other case. **The
correspondence of projects stays confidential**: it still needs the
special rights for correspondence. **Customer, contact and "reported by"**
are seen and changed only by whoever may see customers – otherwise they are
missing on the page and in the form of the case and stay empty through the
interface. The same holds for the interface and the Rentalars app.

**Times on a service case.** Anyone who records times can book times onto
any service case that is not done – even without being planned
or taking part, and with any job function (section 13, "Recording time").
For this, the button **"Record time"** is also at the top of the page of the
case and in every row under "My area" → "Service cases"; it opens the
recording with the case already chosen.

**Where a service case does not appear:** it has no rental period,
reserves nothing and is therefore not in the calendar, timeline,
availability, shortages or the project list, nor under "Coming up" on the
start page. It appears in the search (with "service case"), under
"Projects" → "Open items", among the follow-ups (also under "Planning" →
"Follow-ups"), under "My area" → "Service cases" and on the start page
under "My service cases" – a case in the backlog only once its follow-up
is due.

**PDF for the customer.** On the page of a service case (tab "Overview") the button **"PDF for the customer"** makes a
document you can send to the customer. It holds the overview of the case – number, subject, status, customer,
person responsible, when it was created and its description – and the correspondence, but **only the messages without
lock**, with sender or recipient, date, subject, text and the names of the attachments. Left out: messages with lock,
notes, automatic replies and delivery failures, open items, people taking part, chat, follow-up and every price.
Contact and "Reported by" are in the document only if you may see customers. The PDF is stored at once under
**"Documents"** of the case (not visible to the crew) with the moment in its name; every call makes a new file, earlier
ones stay. The change log of the case notes when a PDF was made. The text is in the language of the company's
documents. You need the right to change the case and to read its correspondence; the person responsible and those
taking part work on the case and may do it without the module "Projects". Note: the PDF is a file of the case like
a mail attachment taken over – **whoever may read the documents of the case can open it**, also someone who may not
see the correspondence or the customers. Messages that are plain HTML appear as text. API:
`POST /api/v1/service-cases/{id}/customer-pdf`.

**If it turns into more** – the customer wants a replacement system with a
technician right away –, **"Turn into a project"** in the head turns the
case into a project. The form is that of a project; it needs a customer
and a rental period. The project keeps the number, mails, files, open items
and history and starts as an inquiry; then you plan material and personnel
as always. People taking part in the case no longer mean anything in the
project – plan them in there as crew.

#### Monthly statement

You bill a customer's service cases together per month:
**Accounting → "Monthly statement"** – for everyone who may see prices
(below, "Who may"). It is in the menu entry **Accounting** next to the outgoing documents
(section 11, "Outgoing documents"). Set a bookmark to the old address
anew.

**The overview.** Under **"Month"** you choose the month; the previous one
is shown first, ‹ and › page through. Per customer there is a row with
their service cases, the hours, the net amount and the status – "open",
"draft", "Invoice RE-…" or "marked as invoiced" – and the button **"Make
draft"** or **"Open draft"**. Whoever may approve times also sees how many
times of the month have no project yet: they belong to no case and are not
billed until they are assigned to one under Personnel → Approve.

**Which cases.** Cases with a customer that were set to "done" in the
month or have approved times or expenses in it. A case done in the month
also brings along earlier approved times and expenses that no statement
has billed yet. Not included are internal cases, cases with "No invoice",
with an invoice of their own or with "Invoice issued" ticked by hand
(section 11, "Invoices still to be written") and cases in another draft.
Each time and each expense is billed by exactly one statement – even if its
line was removed there. A case running over several months is thus billed
month by month. There is one draft per customer and month; cases that come
in later are taken into it by "Collect again" ("not in the draft yet"), and
after the invoice a further statement can be made for them.

**The draft** has a section per case "Service case 2027-0043 – title"; the
number leads to the case:

- **"Activity"** – appears on the invoice below the case. Proposed from the
  description of the case, the notes of the times and – if you may read the
  correspondence – the notes and subjects of the mails of the month; change
  it as you like. If an AI for summaries is switched on and reachable
  (section 16, "AI"), **"Summarise with the local AI"** or **"Summarise with
  AI"** writes it anew; the text then carries "made by AI". The button is
  there for whoever may read the correspondence.
- the **lines** with title, quantity, unit, unit price and tax rate – all
  changeable; a changed one carries "changed". The bin removes a line;
  removed ones are listed collapsed below ("… position removed – not
  billed") with **"Take it back in"**.
- **"Add position"** for material used or sold, a trip …: article no.,
  title, quantity, unit, unit price and tax rate. With an article number
  the empty fields come from the product, for a product for sale its sale
  price.
- **"Take the case out of the statement"** – its times and expenses are
  then free again for another statement.

Hints on a case name what is missing – such as times of the month that are
not approved yet. Below are the totals: net, tax per tax rate, gross.

**How the lines come about.** The approved times count per job function,
at the price of its service product: by the hour or by effort the hours,
per day the days per person (two people on one day are two days), flat
once per case. Hours of a day beyond the limit appear as a line of their
own at the price from the limit, surcharges for night, Sunday and holidays
as for crew lines (section 12, "What personnel costs and earns"). There
are no automatic discounts. Each approved expense becomes a line – a trip
with your own car with kilometres × rate, otherwise its amount –, as a net
price at the default tax rate; if a receipt includes VAT, correct the price
in the draft. A job function without a price gives €0 and a hint.

**Saving, collecting again, deleting.** **"Save"** keeps what you changed;
every other button saves it first as well. **"Collect again"** adds new
times, expenses and cases of the month. Activity texts, added and removed
lines and your changed lines stay; a changed line whose times have changed
since is calculated anew, and Rentalars says so on it. A case that is now
billed otherwise drops out; one you took out does not come back. **"Delete
draft"** frees the cases, times and expenses again.

**Make invoice** – if Rentalars writes the invoices (section 11, "Invoices
in another program"). Above the cases is the **"Introduction of the
invoice"**, preset with "For the service cases of March 2027 we invoice:".
**"Draft as PDF"** shows the invoice with "DRAFT", **"Make invoice"** makes
it after a confirmation: one invoice with a section per case – title,
activity, lines –, numbered from the range of the invoices, with PDF and
XRechnung; closing text and footer come from the invoice template. It
belongs to the case with the lowest number and bills all the cases; the
page says so beforehand (section 11, "Invoice and XRechnung").

**Mark as invoiced** – if you write the invoices in another program. The
box **"To copy into your accounting program"** shows customer, month and
per case the activity and lines; a click copies a value. **"Copy all
positions as a table"** and the field below deliver all lines separated by
tabs, for a spreadsheet, say. Afterwards **"Mark as invoiced"** ticks
"Invoice issued" on every case; **"Take the mark back"** undoes it.

**On the service case** it says at the top where it is billed: "Billed with
the monthly invoice RE-… (March 2027)", "Marked as invoiced with the
monthly statement March 2027" or "In the monthly statement March 2027
(draft)", with "Open the statement" – for everyone who may see prices.
Billed cases count as invoiced; Rentalars no longer reminds you of them
(section 11, "Invoices still to be written").

**Who may.** The monthly statement can be seen by whoever may read
projects, see prices and customers and read each of its cases; made and
changed by whoever may edit projects and each of its cases; a draft
deleted by whoever may delete in projects. The interface offers the same
(section 16, "API tokens").

---

## 8. Prices

*For everyone with the right "See prices and calculation".*

### How the amount of a line comes about

When it is added, the line takes over price, billing mode and tax rate from
the product. After that the price belongs to the line: if the price of the
product changes later, existing projects stay as they were – for inquiries
and options, however, the planning offers to take over the new prices
(below, "Changed products").

For the daily rental:

> **Amount = quantity × unit price × factor of the rental days, minus discount**

The column "Rental days" shows what was used in the calculation: at the
top the days ("2 days"), below it the scale factor ("factor 1.5"). So two
rental days cost one and a half times one day – not two times one and a
half.

> **Example.** 4 spotlights at €20.00 per day, 2 rental days:
> 4 × €20.00 × 1.5 = **€120.00**. With a 10 % discount: €108.00.

**Which rental days apply?** The most precise information applies:

1. rental days **entered** on the line;
2. otherwise the line's **own period**, if it differs from the project:
   every 24 hours begun are one day;
3. otherwise the rental days of the group;
4. otherwise those of the project.

So if you move a line to other days, Rentalars recalculates its rental days
by itself – you do not have to add anything. Below the number it says
where it comes from ("from the period of this line", "as the group"). If
you want to charge something different from what the period gives, you
enter the rental days on the line; that always takes precedence.

A group "Aufbautag" can thus cost only one day while the rest
runs for three days.

**For the project as a whole, rental days and period stay independent:**
"material out of the warehouse" decides when the material is taken, the rental days of the
project decide what it costs.

**Scale factor by hand.** If you enter a factor in the dialog, it applies
instead of the value from the scale – for the special arrangement with a
regular customer.

### Changed products (old prices and texts)

A product becomes more expensive, gets another name, unit or tax rate, but
the offer has already been planned? As long as a project is an **inquiry**,
an **option** or "Confirmed – details open", Rentalars notices:

- **On every page of the project** a hint below the head says "3 lines differ
  from their products" with a link to the planning – also on the tab
  "Overview", where you land when you open a project.
- **The project manager and the members who may edit are notified** as soon as
  somebody saves the product (the bell; whether also by e-mail everybody sets in
  their settings). The notification names no prices.
- **The planning** shows the list "Old and new values" at the top: for each line
  what changed (name, unit, tax rate, billing mode, price), each old → new. This
  applies to material and to personnel (there only the price, which comes from the
  service product of the job function; along with the price come the limit in hours
  per day and the price from the limit onwards, section 12).

What you can do:

- **"Take over the changes"** switches all lines where you had not changed anything
  by hand.
- **"Take over"** switches a single line.
- Lines where someone changed a value **by hand** (a special price, an own title)
  carry the label "set by hand". They stay until you choose "Take over" or
  **"Keep own values"** line by line; after that, Rentalars no longer reports this change.
- **On the product page** the section "Planned in projects that are not fully
  confirmed yet" names all projects in which the product is out of date. There you take over
  the changes per project or "in all these projects" – those you may edit. After
  saving a product a message says in how many projects it has to be followed up.

You see and take over prices only with the right "See prices and calculation";
without it names, units and tax rates work, and the price stays for somebody who
has the right. Quantity, period, note and discount of a line stay as they are when
switching. **Confirmed projects** (status "Confirmed" and all after it) keep their values
without a hint – what has been agreed has been agreed.

### Discounts

- **Per line:** "Discount in percent" in the dialog of the line. If the
  customer has a **default discount** (section 6), it is already entered
  in every new material line – changeable like any other.
- **Per crew line:** likewise "Discount in percent", in the dialog of the
  crew line (section 12). New crew lines start at 0 %; the customer's
  default discount does not apply to them.
- **Per vehicle booking**: "Discount in percent" in the
  dialog of the booking, at most the maximum discount of its product
  (section 7, "Logistics"); the customer's default discount does not apply
  here either.
- **Per group:** in the dialog of the group, as a percentage or as an
  amount.
- **Flat price of the group:** replaces the total of its lines completely.
  The unit prices stay visible; the planning shows how far below them the
  flat price lies.
- **With nested groups** (section 7), first the discount of the subgroup
  applies, then the discount of the parent group to everything in it – its
  own lines and the subtotals of its subgroups, surcharges in the subgroups
  included. A flat price of the parent group replaces everything below it.

**The overall discount**. A discount on the whole project
instead of on single lines: below the totals of the planning **"Set an
overall discount"** (if the project has one already, **"Change the overall
discount"**). You enter either a **percentage** (0 to 100), an **amount
in euros** or a **target amount** (below), never several of
them; emptying the fields removes the discount. Whoever may see prices and
plan the project may do it – a closed project or one that can no longer be
planned does not accept it.

**A target amount instead of a percentage**. You have agreed a
price with the customer: "all in all 15,500 euros" for a project that comes to 17,500 before the discount. In the dialog, under
**"Target amount net"** or **"Target amount gross"**, type the total the
project should come to after the discount. Rentalars works out the
percentage, with up to six decimal places, and stores it. Above the fields the
dialog says what the project comes to before the discount (net and gross),
and while you type, a preview shows the **stored percentage** and the total
that results ("Stored percentage: 11.428571 %. Discount …; the project then
comes to … net, … gross."). The gross amount is worked out with the tax of
every rate of the project, as the invoice will; if the cent cannot be reached
exactly because of the rounding of the tax, Rentalars takes the nearest
amount and says so ("The target … cannot be reached to the cent – this is the
nearest amount."). A target above the total without discount is refused,
because a discount cannot raise it.

Note that **only the percentage is stored**. If you add material afterwards,
the percentage stays and the total changes with it; if the price is to stay
fixed, enter the target amount again. Offers, order confirmations and
invoices, the price overview and its CSV file print the percentage with **up
to six decimal places**, without needless zeros ("Overall discount 19.99994 %",
but "Overall discount 10 %"), so the printed percentage gives the printed
discount to the cent; the calculation uses the stored value. Above roughly a
million euros net a target amount can no longer be met to the cent exactly;
Rentalars then takes the nearest amount.

The overall discount is taken off **last**: from the net total after all
lines, discounts, surcharges, rounding and the minimum rental. An amount is
at most as large as the total; with a total of zero or less there is no
discount. The totals show **"Sum before the overall discount"**,
**"Overall discount 10 %"** and below it the new net total; tax is
calculated on the reduced total, in proportion per tax rate. The price
overview (PDF and CSV), offer, order confirmation and invoice carry it as
**a line of its own, "Overall discount 10 %"**, at the end; the electronic
invoice (XRechnung) and the DATEV export carry it, too.

Good to know:

- It holds **per project**. A subproject has its own; in a whole project
  each project has its row, and the totals of the whole project add them up.
- It is **not a discount per line**. The limits "Maximum discount per job
  function" and "per product" (below) and the rule for crew lines apply
  only to the discounts of lines and groups, not to it.
- In the **follow-up costing** (yield per line, profit) it works on the
  project total; it is shared over material, personnel and vehicles in
  proportion, not over single lines.
- **Duplicating** copies it – for whoever may see prices, and only if
  material, crew or vehicles are copied too. **Splitting** always takes it
  over so that no price changes: a percentage into every part, an amount in
  proportion to the sums of the parts. Whoever may not see prices sees it
  nowhere, not even in the API.
- The change is in the project's history. API: `overall_discount_percent`
  and `overall_discount_amount` on the project, `net_before_overall_discount`
  and `overall_discount` in the totals.

**Maximum discount per job function.** Some services should never be
discounted, or only a little – the rigger, for instance. For this you set
a **"maximum discount in percent"** on the job function ("Personnel" →
"Job functions", section 12): empty means no limit, 0 means never
discounted. The limit applies to crew lines of this job function and to
older material lines with its service product – to their own discount, to the customer's standard
discount and to their share of the discount or flat price of the group.
What a line may not take does not pass on to others: the discount of the
group then turns out smaller, a flat price correspondingly higher. If the
limit applies, planning and price overview show "at most 5 % (job
function)" on the line; values entered stay, but the calculation uses the
limit. Only those who may see prices may see and change the limit.

**Maximum discount per product.** The same exists on every product
(section 5, "Creating a product"), for instance for consumables or goods
for sale. If its limit applies, the line shows "at most 5 % (product)". If
both product and job function have a limit, the stricter one counts. Crew
lines are limited by the job function only.

### Surcharges

Surcharges are products of the kind "surcharge" – a **fixed amount**
("Expresszuschlag €50") or a **percentage** ("Außeneinsatz 10 %"). You
add them like any other product. The surcharges for night, Sunday and
holiday hours of the personnel are not a surcharge in this sense: Rentalars calculates them on each crew line itself (section
12, "Surcharges for night, Sunday and holidays").

For a **percentage** surcharge, you set in the dialog of the line **what it
refers to**: the whole project, individual groups or individual lines –
several, too. Below the surcharge the planning shows what it is calculated
on and from which amount.

The percentage is calculated on the amounts **after discount** and **never
on other surcharges**. A surcharge on the whole project is also calculated
on personnel and logistics; optional groups and optional or alternative
lines do not count for it.

> **Example.** Außeneinsatz 10 % on the groups "Licht
> Front-Traverse" (€321.00) and "Licht Rear-Traverse" (€351.00):
> 10 % of €672.00 = **€67.20**.

### The totals

At the bottom of the planning page:

```
Groups                                  €1,329.00
Without group                             €272.20
Personnel                               €1,666.00
Surcharges                                 €67.20
Total net                               €3,334.40
Tax 19 % on €3,334.40                     €633.54
Total gross                             €3,967.94
Optional groups, not included             €135.00
Optional lines, not included               €48.00
Costs of personnel (planned)            €1,294.00
Expenses and travel costs (approved)       €84.00
Contribution margin                     €1,956.40
```

"Personnel" is the subtotal of the block Personnel (section 12) – surcharges
for night, Sunday and holidays are included in it. If the project has
vehicles, **"Logistics"** follows, the subtotal of the block
Logistics (section 7, "Logistics"), and – with the right for purchase
prices – **"Costs of the vehicles"** among the costs. While driven
kilometres are missing, the net total says "contains estimates". The personnel costs and
the approved **expenses and travel costs** of the crew (section 13,
"Expenses and travel costs") are only seen by those who may see hourly and
day rates and personnel costs. Optional and alternative lines, if there are
any, are listed separately below the gross total ("Optional lines, not
included", "Alternative lines, not included"). **Customer material** counts
towards no total and is not listed below it either: it is never charged
(section 5, "Customer material").

If a project has lines with different tax rates, the tax is shown per tax
rate. If it contains estimated quantities (billing by effort), the net
total says "contains estimates".

Those who may additionally see purchase prices and personnel costs see the
costs of the subrentals and of the personnel and the **contribution
margin**: the net total minus
these costs, the approved expenses and the
costs of the vehicles. Where it is
shown per row – in the project list, in the price overview per job
function –, the column is simply called "Profit".

Totals are not stored anywhere. They are calculated from the lines each
time they are called up and can therefore never differ from them.

### The price overview

The tab **Price overview** shows the same as a tidy working document: for
each group a table with article number, name, quantity, unit, rental days,
unit price, discount and amount; in addition the personnel as a block of
its own with the article number of its service product, hours or days,
price and amount – and, where a limit per day is exceeded, below the price
"of which 2 h beyond 10 h a day at €55.00" (section 12, "What personnel
costs and earns"), and where surcharges for night, Sunday and holidays
apply, "incl. surcharges …" with each kind; below the block is their total
("Included: surcharges for night, Sunday and holidays of … (before
discounts)."); each row is named like its rule under
"Settings" → "Surcharges". Hourly and day rates and wishes for particular
items never appear there; costs only in the breakdown per phase, with the
right for it (below).

Optional and alternative lines appear in it with their label and do not
count towards the total; below an alternative it says what it could
replace ("alternative to "8 × LED-Scheinwerfer""). Subgroups appear
indented within their parent group, the parent group with its "Subtotal
with subgroups".

The block **"Logistics"** follows the personnel: per vehicle
booking article number, name, quantity – kilometres, days or flat rates –,
unit, unit price, discount and amount, with the trailer surcharge in it;
PDF and CSV take it over. Internal costs never appear there.

**Personnel by phase and function.** The button **"Personnel by phase and
function"** breaks down the block Personnel: for each phase one row per job
function with places, hours or days and amount, below that the subtotal of
the phase; personnel without a phase comes last under "Without phase".
That way you see, for instance, what setup and show cost per sound
engineering. Those with the right for personnel costs also see the columns
"Costs" and "Profit" in this view. **"Personnel as the other blocks"**
switches back. PDF and CSV take over the chosen view – without costs,
since the PDF goes to customers.

**Whole project and subprojects.** The price overview of a whole project
first shows its own lines, then each subproject with number, name and
period and its total, and at the bottom the **"Totals of the whole project
with all subprojects"**: net, tax per tax rate and gross across everything.
Each subproject calculates on its own – a percentage surcharge "on the
whole project" on the whole project only applies to its own lines.
Cancelled subprojects are missing and are named; subprojects you may not
read are missing too, and the page says how many. Lines taken over appear
in it with "taken over" and "not charged / charged in …". The price
overview of a subproject only shows that subproject, with the hint "Part of
…; the sum of all parts is in the whole project" and a link there.

The overview is built for further use: **a click on an amount or text
copies it** to the clipboard. "Groups with totals only" hides the lines,
"Groups with all lines" brings them back. Rentalars writes offer, order
confirmation and invoice itself (section 11).

**As PDF and as CSV.** At the top right, **"PDF"** delivers the overview as
a file for printing or passing on, **"CSV"** the same figures for the
spreadsheet (semicolon, decimal comma). Both take the view currently
chosen: all lines or only the groups with their totals, the personnel as a
block or by phase and function – for a whole project with the subprojects
you may read.

**What a group contains.** Without lines, there is a line below each group
summing up what it contains:

> **Licht Front-Traverse** – 8 × LED-Scheinwerfer RGBW, 6 × Traverse
> 4-Punkt 2 m, 2 × Kettenzug 500 kg and 3 more items … €420.00

That way the customer knows roughly what the amount stands for without
reading every cable. Identical products are added up, a kit is called like
the kit. At most six things are named – the most valuable ones, in the
order of the planning –, the rest as "and … more items". Subrentals that
only cover a shortage do not appear; the customer sees the line they cover.

As a PDF, the price overview can be attached to a mail (section 14) – for a
whole project then with all subprojects that are not cancelled, as in the
offer and the invoice.

### Totals in the project list

What will next month's projects bring in, how many man-hours are planned?
In the project list ("Projects") you can also show totals via
**"Columns"** (section 2, "Lists") – none of them is shown by default:

| Column | What it contains |
|---|---|
| **Planned man-hours** | the planned hours of all crew lines |
| **Material revenue** | total net without the personnel and the logistics: groups, lines without group, surcharges |
| **Personnel revenue** | what the customer pays for the personnel |
| **Logistics revenue** | what the customer pays for vehicles and trailers |
| **Total net**, **Total gross** | as in the planning |
| **Material costs** | what the subrentals cost |
| **Personnel costs** | what the personnel costs (planned) |
| **Logistics costs** | the internal costs of the vehicles and what vehicles from suppliers cost |
| **Profit** | the contribution margin: total net minus all costs and the approved expenses |

Material, personnel and logistics revenue add up to the total net. A **whole
project** shows the sum of itself and its subprojects (without cancelled
ones), like its price overview and its offer; each subproject shows its own
totals in its row. If both are in the list, a subproject counts twice when
the column is added up.

Who sees what is as in the planning: revenue and totals only with the right
to see prices; material and logistics costs additionally with the right for
purchase prices; personnel costs with the right for personnel costs; the
profit only with all three. Everyone who sees the list sees the man-hours. For projects
you only know through your deployment, the fields stay empty. A click on these columns sorts by them too – for up to 2,000 projects in
the filtered list; with more, the list stays in its usual order, and a hint
asks you to narrow it down with the filters (section 2, "Lists"). They are
included in the CSV export if they are shown (or with "CSV with all
columns").

### Reports

Do the projects, the customers, the material pay off? The
sidebar has **"Reports"** for this – for everyone whose role may read the
module Reports and every project and who may see prices. The figures come from the calculation of the
planning, as in the price overview and the totals of the project list
(above); nothing is stored.

**Tab "Profitability".** At the top you choose a **"Year"** or a period
("or from" … "until") and, if you wish, **"closed projects only"**, then
"Show". Whole projects with their subprojects count from the status
"Confirmed – details open" on, without cancelled ones, each in the month
their material comes back; service cases do not. The page shows

- at the top the totals: number of projects, **"Revenue net"** (material,
  personnel and logistics), **"Costs"** (subrentals, crew,
  approved expenses and the costs of the vehicles) and the **"Profit"** –
  what is left over – with its share of the revenue;
- **"Per month"** one row per month with revenue, costs, profit and
  **"Margin"** in percent, plus bars for revenue and profit;
- **"Per customer"** and **"Per project manager"** the same, summed up;
- **"Most left over"** and **"Least left over"** – the projects with the
  largest and the smallest profit.

**Calculated values.** "Revenue" and "profit" here are **calculated**: they
come from the price planning of the projects, not from issued invoices,
payments received or booked expenses – the page says so, and the columns are
called "Calculated revenue net", "Calculated profit" and "Calculated margin".
The books are in Accounting.

**"CSV of the projects"** delivers the projects of the period with their
figures for the spreadsheet. Who sees what is as in the project list: the
page shows costs and profit only with the rights to see purchase prices
and personnel costs. In the CSV file the costs of subrentals and the
logistics costs appear with the right for purchase prices alone, those of
the crew and the expenses with the right for personnel costs, the profit
only with both; the logistics revenue stands next to material and
personnel revenue.

**Tab "Material"** – with the right to see purchase prices: per product
the number of **items**, their **purchase prices**, what the product's
lines **earned** after discounts, and the **"Share of the purchase
price"** in percent. Under **"Earned in"** you choose "All time" or a
year. How it is calculated – only projects whose material went out, a
kit's line shared out to its components by their prices, a set bought
together with its price – is in section 4, "What an item earns"; the
share of each single item is there too.

---

## 9. Availability, shortages, subrental

### How Rentalars calculates

> **Free = plannable stock − highest simultaneous reservation in the period**

What counts is the *highest simultaneous* use, not the sum: two projects
that use the same six cables one after the other need six cables, not
twelve.

> **Example.** Stock: 9 XLR cables.
> Project A (confirmed) has 6 cables from the 10th to the 12th.
> Project B needs cables from the 11th to the 13th.
> In B's period at most 6 are away at the same time – **3 are free**.
> If B books four cables, one is missing.

The following applies:

- The calculation uses **date and time**. What comes back at 10:00 can
  go out again at 10:00.
- **Plannable** is what is available or in use and not permanently
  installed in something else. Defective, blocked and retired items do not
  count. An item with a **blocked period** is only missing during that
  period (section 4).
- Confirmed projects and those that are out reserve **firmly**.
  **Options**, **optional groups** and **optional or alternative lines**
  only pencil in – they make other lines "tight", not "red". Inquiries
  reserve nothing.
- **Kits** take up their components. **Cases** take up their loose contents
  – except those taken out for this project (section 4).
- **Sold goods** do not come back: they are gone for good from the start of
  the project.
- If a project is **overdue** – still "out" although it should be back –,
  its material still counts as taken – until it is booked back, also for the days to come.
- **Material taken back** is free again for other projects from the
  booking ("Book the return") – even if the rest of the project is still
  out (section 10, "Taking back").
- **Subprojects** take up material like projects of their own, each with
  its period and status. If two stages of the same whole project need the
  same material at the same time, the shortage shows it – and the tab
  "Subprojects" names these bottlenecks separately.
- **Material taken over** (section 7, "Subprojects") counts as out without a
  break, from the earlier stage until the end of the later one, without
  buffer times in between.

Every project is assessed **as if it were confirmed**. So even an inquiry
already shows whether the material would be enough.

If two confirmed projects together have booked more than there is, **both**
show the shortage. You decide who backs down – not the order in which they
were entered.

### Buffer times

Material needs time for checking, loading, cleaning. Under "Settings" →
"Company data and settings" you set how many hours **before** and
**after** each deployment the material additionally counts as taken
(default: 0). A category can differ from this (fog machines take longer),
and so can a single product.

### The "Shortages" page

**"Planning" → "Shortages":** all open shortages of all running and coming
projects at a glance: project, product, period, number of pieces missing –
if you like, only the next few weeks, or summarised **by product**
("Missing at most"). Below that, all **subrentals** with supplier and
status; a click on the name of a supplier opens the page "Subrental at …"
of the project (below, "Subrenting"); without a supplier it says "open"
there. The filter **"Supplier"** shows only the subrentals at one supplier
("Subrentals at Verleih Nord") – "Show the subrentals at this supplier" in
its master data also leads there. A good start to the day for everyone who
does the scheduling; the first open shortages are also shown on the start
page (section 2), and under "Projects" → "Open items" each one is listed
with its project (section 7, "Schedule"). In addition, Rentalars reports new
shortages to the project manager – when and how far ahead is set under
Settings → Notifications (by default every day at 4:15 for the coming four
weeks; section 16).

The availability of material is a **special right**: "See
availability of material". Without it the Shortages page, the material
utilisation, the traffic lights, the "Availability" box and the timeline
of products and material, the shortages on the start page and among the
open items are missing, and no notifications about shortages arrive. All
roles supplied except Crew have it (section 16, "Roles and rights").

If a subproject is short of something because other subprojects of the
same whole project take up the material at the same time, it says **"of
these held by other subprojects: N"** – with a link to the tab
"Subprojects". If the pieces are needed not at the same time but one after
the other, and only the buffer times are in the way, a takeover helps
(section 7).

**A replacement before the subrental**. If the product of a short
line has **replacements** (section 5, "Accessories and replacements"), the
panel "Suggestions for the planning" above the lines names them with what is
free of each in the period of the line – "2 pieces are missing → Speaker 12b,
3 free, covers it" – and adds a line for the replacement with one click
(section 7, "Accessories and replacements in the planning"). The same panel
catches a line whose product has been deactivated. Replacements are
suggested only to whoever has the special right "See availability of material"
(whoever lacks it does not see which lines are short either). It is a suggestion: the shortage stays on this page until you
have closed the gap.

### Subrenting

If something is missing, the red line offers a button: **"Subrent 2 ×
L-010"** – except for customer material, which nobody else can supply
("Customer material cannot be subrented."). It opens a window "Add
subrental", in which you enter:

- **"Quantity"** – the shortage is suggested.
- **"Supplier"** – type: Rentalars suggests matching suppliers from the
  suppliers ("Settings" → "Suppliers"), by name, contact or e-mail. If it
  does not exist yet, choose the last suggestion **Create "…" as a new
  supplier**: a second window "New supplier" opens above the subrental,
  with what you typed as the name; you enter contact, e-mail, phone and
  "our customer number there" and press "Save supplier" – everything you
  have already entered in the subrental stays put. Leaving it empty is fine
  too, as long as nobody has been asked yet.
- **"Purchase price per unit"** – what the supplier charges for the whole
  period. This needs the right to see purchase prices.
- **"Status"**: **open** (default) → requested → ordered → received →
  returned. Every status except "open" needs a supplier ("Without a
  supplier the status can only be "open".") – "requested" from nobody does
  not exist.

The window does not ask for a rental price: the customer pays the original
line at the normal price, the subrental itself is **not charged** to them.
"Add subrental" – and the shortage has disappeared.

Afterwards the subrental appears **indented directly below its line**, as
part of it and not as a further line: "↳ 2 of these are subrented from
Verleih Nord · ordered · purchase price €15.00 per pcs. (€30.00)". It has
no amount of its own and no copy icon. With the pencil and bin in this row
you edit or delete it; the dialog has title, quantity, period, supplier,
status, purchase price, **"Picked up at the supplier"** and note, but no
group and no prices. You set the tick if you fetch the material from the
supplier yourselves and bring it back – then pickup and return are part of
the trips of the project (section 7, "The trips of a project"); without
the tick, the supplier delivers and collects. If you move the line – by
dragging, via the dialog or with the selection –, the subrental moves
along. The purchase price goes into the costs of the project and thus
into the contribution margin. If you copy a subrental – with the project,
with its group or as a line –, the copy is set to "open".

**Subrenting without a shortage** – something you do not have in stock at
all: add the product `E-001 Subrental` like any other line, give it a
meaningful title in the dialog ("Hazer Tour Hazer II"), the price for the
customer, supplier and purchase price.

**The page "Subrental at …".** The name of the supplier on a subrental – in
the planning and under "Planning" → "Shortages" – opens the page
**"Subrental at Verleih Nord"** of this project. It belongs to the planning
("Planning" at the top leads back) and shows at the top the details of the
supplier – contact, e-mail, phone, your customer number there and its
address with "Route in Google Maps" from your location and "Show map"
(section 6, "Route and map"); "Edit supplier" is there for those who may
change the settings –, then three parts:

- **"Subrented":** everything you have subrented from them for this
  project, with period, status and **"Picked up"** – ticked "Picked up at
  the supplier", otherwise "delivered" –, with the right for purchase
  prices also the "Purchase price per unit", the "Purchase" per row and
  "Purchase in total". You change status, pickup and purchase prices here
  for all rows at once: **"Save status, pickup and prices"**.
- **"Documents of the supplier":** offers, order confirmations, delivery
  notes and invoices. Under **"Add a document"** choose the file, the
  **"Kind of document"** (offer, order confirmation, delivery note,
  invoice, other) and, if you like, a title, "Upload". The documents also
  appear in the tab "Documents" among the files of the project (section
  11); the crew does not see them.
- **"Correspondence":** the mails of the project from and to the e-mail
  address of the supplier – they appear on their own, both when fetching
  and when sending. **"Write mail"** writes to them, with their address as
  recipient, "Subrental for …" and the code of the project in the subject;
  the replies come into the project and are shown here. If a mail from
  another address belongs to it, you assign it on the page of the mail
  under **"Belongs to a subrental?"** (section 14). If the supplier has no
  e-mail address yet, the page says so; enter it in the master data
  (section 16, "Master data").

Anyone who may read the planning of the project may read the page; status,
prices and documents may be changed by anyone who may edit the project, as
long as it is not closed. Purchase prices, mails and writing mails need
their special rights as everywhere.

**Subrental no longer needed.** If the covered line becomes smaller or own
material becomes free, the planning points it out: "A subrental is no
longer needed in full". Rentalars does not delete it by itself – the order
with the supplier may already be running.

Subrented material appears on the packing list with the hint "subrental" and
the supplier.

---

## 10. Packing, issue, return

*For everyone with access to "Packing and issue". The page is built for
the phone: large buttons you can hit even with gloves on.*

The principle: **you pack by product and quantity.** Nobody has to pick
out or scan individual items. "12 × XLR cable 5 m" means: take twelve
from the shelf, tick them off. Where the individual piece does matter –
the rack with its contents, the device with its inspection – you can
choose items; it is never required.

Issue and return work the same way: **tick, then book**. When packing,
you tick what is packed, and "Issue" books it out of the warehouse; on
return, you tick what is back, and "Book the return" books it into the
warehouse. Both can be done in parts and side by side.

Without a network – in the truck, in a hall without reception – you tick
with the **Rentalars app for Android**; as soon as the phone has a network
again, the ticks arrive here. Issuing and "Book the return" remain a step
in the browser (section 2, "The Rentalars app for Android").

### The packing list

The **Packing list** tab in the project. As soon as a project is confirmed
("Confirmed – details open", "Confirmed") or is out, it has its
packing list – even if nobody has opened it yet, so that the Companion app
finds it. The list is made from the planning and is always up to date
with it:

- one row per product and line, structured by groups and their
  subgroups;
- **kits are broken down** into their components ("4 × Active speaker
  12 inch, from 4 × Active speaker kit");
- services, incidental costs and surcharges are left out – they cannot
  be packed;
  so are optional and alternative lines and groups, as long as they are
  not set to "normal" (section 7);
- sale goods and subrentals are marked, as are takeovers from other
  subprojects (below, "Takeover and handover between subprojects"), and
  the customer's material with **"customer material – taken along"** –
  with weight, volume and storage location like your own (section 5,
  "Customer material");
- the note of the line is shown – and the **wish** for a particular model
  or item ("Wish: 0742"). If the line stands for several pieces
  and only some of them are wished for, it says so – "Wish: item 0042
  (Cordial CPM 5 FM) – 1 of 10 pieces" – and the row lists below it exactly the
  items to take: **"Wished: 0042 Cordial CPM 5 FM, 03-A-1"** with their storage
  spot, until they are chosen. The PDF and the interface show the same.

Below a row, where needed, there are **hints** for the warehouse:

- "also in: Hall 2 > Shelf C" – in the order by storage location, when
  the product is kept in several places;
- "in containers: 0123 in 0500" – pieces that are currently lying in a
  case;
- "2 item(s) in stock with an overdue inspection" (section 4,
  "Inspections");
- "0123 Wireless microphone stays behind (taken out of 0500)" – on the
  row of the case, when some of its contents stay in the warehouse for
  this project (section 4).

**PDF to print** (top right) produces the list for the clipboard: with
the company letterhead, boxes to tick and fields for signature and date –
in the order you have chosen, with weight and volume and, if shown, with
the contents of the containers.

**"Loaded into"**. If vehicles are booked in the project
(section 7, "Logistics"), you choose at the bottom of the packing list
under **"Loaded into"** which vehicle it is loaded into, and save. The
head of the packing list and its PDF then name it. If the project has
several packing lists – one per truck, say (below) –, you choose it for
each. Whoever may pack may do this, as long as the packing list has not
been taken back.

### Order, weight and contents

Above the list, under **"Order"**, you choose how the rows are sorted:

- **"Groups"** – as in the planning (the default);
- **"Category"** – all cables together, all lights together;
- **"Storage location"** – grouped by the place where most pieces of the
  product are kept, with the place on every row. That gives you the
  **walking route** through the warehouse; anything without a storage
  location comes at the end under "Without storage location".

The choice applies to all packing lists and to the PDF too, until you change
it or log out.

**"Show contents of containers"** lists, indented below a rack or case,
what is inside it – for chosen items, or when there is only one of the
product. "Hide contents of containers" makes the list short again. **Bulk
material built into** the case (section 4, "Built-in bulk material") is
listed under the row of the case – "contains 10 m × XLR cable" – as soon as the
case is chosen or is the only one, whether the other contents are shown or not;
it goes out with the case and is not counted a second time.

**Weight and volume.** Above the list you see roughly what the load
weighs and how much space it needs – "about 412 kg, 1,830 l" – and each
group shows its weight. The calculation uses the weight and dimensions of
the models (section 4); if a product has models of different weights, the
heaviest counts, so that the total is never too light for the truck. If
some rows lack these details, it says how many ("3 rows without weight")
– the total is then a lower bound.

### Several packing lists

**When several packing lists?** You don't need them: one packing list per project
is the normal case, and every project has it automatically. Several are
worthwhile when the material of a project leaves the warehouse in separate
loads – for example

- **two trucks** that are loaded separately and leave at different
  times;
- **sound and light** from different halls or warehouses, packed by
  different people;
- an **advance load** – trusses and rigging days before the rest,
  because setup starts earlier.

Then each load has its own packing list with its own title ("Truck 2"), its
own note, its own loading time, its own PDF and its own state – packed,
issued, back. Each is issued on its own, article by article (below,
"Issuing"), and for each you can make its own delivery note (section 11).
A load that just leaves later but is packed by the same people at the same
place doesn't need a packing list of its own: a partial issue is enough for
that.

This is how you split:

1. Above the packing list there is a tab for each packing list (for a whole
   project and its subprojects, also the other parts, see below "The
   packing list of the whole project"). **"+ Packing list"** next to them asks for
   **Title** ("Truck 2"), **Loading** (date and time) and **Note**;
   "Create packing list".
2. A new packing list starts out empty. **"Distribute lines"** shows all lines
   of the project with group and quantity; for each line you choose the
   packing list, then "Save distribution". Every line is on exactly one
   packing list. Ticks of a moved line are dropped; lines whose material has
   already been issued stay where they are.
3. New lines from the planning land on the first packing list.

At the bottom of a further packing list, **"Edit or delete this packing list"**
opens: change title, loading and note ("Save"), or "Delete packing list" –
its lines then go back to the first one. The fields there are
plain text fields like everywhere, and the two buttons stand side by side at
equal size. The first packing list cannot be deleted, nor
can an issued one.

Each packing list is packed, issued and taken back on its own. The project
goes to "Out" as soon as **everything** is out, i.e. every packing list with
material from the warehouse is fully issued – an empty packing list, or one
with only takeovers from other subprojects, does not hold it up. Until
then, an issued packing list says: "The project stays “Confirmed” until the
material of its other packing lists is issued too." It goes to "Returned"
when no packing list is out any more and none is still waiting for its issue.
There is a delivery note per packing list or for all of them together
(section 11).

### Packing

- **The big tick** on the right ticks off the whole row. Tapping it again
  removes the tick.
- **The number field** next to it is for partial quantities: 8 of 12
  packed.
- **"Tick all rows"** at the bottom, when everything is together.

The status of the packing list changes from "open" through "in progress" to
"packed".

**The bar** at the top of the packing list shows, from packing to return,
where the pieces are. It fills from the left:

| Colour | means |
|---|---|
| orange | taken back – booked into the warehouse again or handed over to a later subproject |
| orange hatched | ticked as back, not booked yet |
| green | issued and still out |
| green hatched | packed (ticked), not issued yet |
| grey | in the warehouse |

Below it, the same is shown in words and figures, each with its colour
swatch – for example "4 taken back", "2 ticked as back", "30 issued",
"6 packed", "21 in the warehouse"; whatever there is none of at the moment
is left out.

### Packing with a scan

You can mark an item as packed by **reading its label** instead
of ticking: with the phone's camera, with a hand scanner or by typing the ID.
It is optional – ticking a row works as before, and a scan only counts up the
same tick. Above the list, in "Pack and issue", is the field **"Item is
packed: scan or type the ID"**; type or scan, press **"Count"** (a hand
scanner sends the Enter itself), or open the camera with **"Scan"** (section 4,
"Scanning labels and codes"; the window stays open for the next label).

- Rentalars picks the row of the item's product – the row that has it chosen
  already, otherwise the first one that still needs items – chooses the item
  for it and counts the row up: **"0742 packed: 4 of 6 for Speaker 12."** For a
  product of several pieces it counts per piece, and a piece of a "10-pack"
  counts when its ten items have been scanned.
- Scanning the same label twice does not count twice ("… is already counted
  for …"). The items you scanned **go out first** at the issue.
- **Refused, with the reason:** the item is on no row of this packing list;
  it is defective or blocked; it is chosen for or out with another project;
  all items the row needs are chosen; the material has already been issued.
  An item fixed inside a case is not packed on its own ("… sits in 0500 and
  goes out with it"). Bulk material points you to its row – you enter its
  count there. An **overdue inspection** only warns; you decide.
- The row of the scanned item is highlighted.

**Taking back** works the same way: in the "Take back" view the field says
**"Item is back: scan or type the ID"**. Only an item that went out with this
packing list is counted, and once ("… is already counted as back."); an item
that left inside a case comes back with it. Booking the return stays a step of
its own with "Book the return".

### Choosing items

Usually it doesn't matter which of the twelve cables goes out. Sometimes
it does: it should be wireless rack 0500, because its contents are to go
along; the device with a fresh inspection; the piece whose history you
want to follow. For this, every row (except bulk material and subrentals)
has the link **"choose items"**.

It opens a list of the items of the product. Next to them you see what to
bear in mind – "with 2026-0041", "in 0500", "inspection overdue". Items that
are chosen for another project or are out with it cannot be ticked, nor
can items that have already come back from this project ("came back from
this project") – they do not go out again in it (below, "Taking back").
Tick them, at most as many as the row needs, then "Save choice". The IDs
are then shown on the row; an item with an overdue inspection is
highlighted, and Rentalars warns you as early as when you save. "change
items" changes the choice, as long as the packing list is not fully issued.

What the choice does:

- On issue, **exactly these items** go out; for the remaining pieces of
  the row, what is described under "Issuing" applies.
- The **contents** of a chosen rack or case go out with it and come back
  with the return – permanently installed contents always, loose contents
  unless they have been taken out for this project.
- The **inspection** is checked on issue: if an item with an overdue
  inspection goes out, Rentalars tells you ("0742 went out although its
  inspection is overdue.").

Where the planner **wished for** particular items (section 7), they stand
first in this list, marked **"wished by the planner"**; the packing list
shows them before you have chosen anything (above, "The packing list").

If you don't choose, you pack as before.

### Adding material while packing

While packing you notice that two cable drums are still missing? At the
bottom of the packing list there is the field **"Add material while packing"**:
search for the product, enter the quantity, **"Add as addendum"**.

The line goes into the planning of the project – with the note "Added
while packing" and with a price like any other – and onto this packing list,
already marked as packed. On the packing list and in the PDF it is marked as
**"addendum"**. If the stock is not sufficient, Rentalars tells you
("Shortage: 2 × F-020 are not free in the period."). Only material can be
added – no service, no incidental costs and no surcharge – and only as
long as not everything has been issued.

Material may be added by anyone who may change the project or packs for
all projects – Warehouse and Project management, for example. Everyone
else sees, in place of the field, the note "Only people who may change the
project or pack for all projects may add material while packing."

### Packing with the Crew role

With the Crew role you pack in your own projects – in the
browser and in the app, also without a network: tick off (also by
scanning), choose items, issue and take back, clarify missing parts,
report defects, create, rename and delete further packing lists, move
lines between packing lists, book handovers, take parts out of containers.
You cannot add material: you pack 1:1 what is on the packing list. Extra
material is added by people who may change the project or pack for all
projects; in place of the field you see the note saying so. In the app a
quantity above the packing list is refused, your other ticks arrive.

None of this changes what the project costs: ticking never goes beyond
the packing list, clarifying missing parts is only a note (for single items that did not come back, Rentalars blocks the item when the return is completed, so that it is not promised to the next project; for bulk material it points out that the quantity is to be reduced if the pieces are lost for good), deleting a
packing list moves its lines to the first one, and a handover between
subprojects is charged only once – at the subproject the material comes
from. If the crew should not pack in your company, an administrator sets
"Packing and issue" of the Crew role to "read" (section 16, "Roles and
rights").

### Changes after packing has started

If someone changes the planning while packing is already under way, the
warehouse should notice. Rentalars highlights the changes:

- a **new** row with "new",
- a changed quantity with "was 12" – the quantity before the change,
- a row that has been **dropped** at the top in the box "The planning
  changed since packing started.", struck through and with "no longer
  needed" – if something had already been packed, it says "4 packed, put
  back".

"new" and "was 12" also appear in the PDF. The hints stay until someone
in the warehouse presses **"Changes are dealt with"**.

### Issuing

You issue what you have ticked – article by article, the way it goes onto
the truck. At the bottom of the packing list there are two buttons:

- **"Issue"** books exactly what has been ticked, with the ticked
  quantities, out of the warehouse. Next to it you see how much goes out
  ("12 ticked pieces go out."). If nothing new has been ticked yet, the
  button cannot be pressed.
- **"Issue everything"** books every row with its full quantity, including
  what is not ticked – for when packing was done on paper; Rentalars asks
  first. If everything is already ticked, this button is missing, because
  "Issue" then does the same.
- Sale goods are permanently taken out of the stock (section 5,
  "Consumables and minimum stock").
- The project changes to **"Out"** as soon as everything has been issued
  – with several packing lists, when all of them have been issued.

Which items went out: first the chosen ones, then the wished-for items –
each wished item covers one piece of its line (section 7, "A wish for one
piece of a pack"); beyond that, Rentalars notes them wherever it knows by itself which ones
they must be – for example because all items of a product go out. They are
then set to "in use", and their history shows the project.

After the issue, the material is **out** – that is what every row says,
and that is how the list stays: calm and without red. Out is not the same
as missing.

**Partial issue.** The first truck leaves today, the rest tomorrow? Tick
what goes out today and press "Issue". The packing list is then set to
**"partly issued"** (yellow) and says at the top how much is out and how
much is still missing ("Partly issued: 14 of 63 pieces are out. 49 pieces
are not issued yet."). You simply carry on packing:

- A row that is completely out is grey and marked **"issued"**. It no
  longer has a tick.
- A row of which only part is out shows "4 of 6 issued". Tick the rest as
  soon as it is packed.
- Once the rest is packed, "Issue" books it out. "Issue everything" books
  the whole rest at once.

At the top you switch between **"Pack and issue"** and **"Take back"**.
That way you can take back what is already out while the rest is still
being packed and issued – even back and forth several times: issue, take
back, issue something again, take back again later. Whatever has already
been taken back counts as done and does not go out again in this project;
whatever had not been issued yet you keep packing and issuing. Example:
10 planned, 6 issued, 4 of them taken back – these 4 are done, 2 are
still out, and you can still issue the remaining 4. Until everything is
issued, the project keeps its status, and the packing list says so ("The
project stays “Confirmed” until everything is issued."). The issued
material nevertheless counts as out straight away: it is not free for
other projects, and on the start page the project is listed under "Out at
the moment", with the hint "partly issued". In the PDF, every row shows
what has already been issued.

If the rest is no longer needed, complete the return ("Complete the
return" in the "Take back" view, below): what was not issued stays in the
warehouse, and the project goes to "Returned". If the planning changes
after the issue, press "Changes are dealt with". If the rest is dropped,
the packing list is then set to "issued". If a line is added, it goes back to
"partly issued", and the new line can be packed and issued.

**Issued by mistake?** "Take back the issue" undoes all issues of this
packing list, as long as nothing has been ticked as back yet. The ticks stay. The project then has the status it had before the issue – an option stays an option.

### Taking back

When the material comes back, you open the same page – after a partial
issue with **"Take back"** at the top. It now shows the issued quantities.
The return works like the issue: tick first, then book.

- **Tick** for "completely back", **number field** for partial
  quantities.
- **"Everything is back"** ticks everything that is out.
- **"Book the return"** at the bottom books exactly what has been ticked
  into the warehouse. Next to it you see how much comes back ("6 ticked
  pieces come back."); if nothing new has been ticked, the button cannot
  be pressed.

This works as soon as something is out – even while the rest is still
being packed and issued (above, "Partial issue"). Whatever is booked is
**free again straight away** for other projects (section 9). Once a row
has been taken back completely, its items – including their contents –
are set to "available" again, and the row no longer has a tick; as long as
only part of a row is back, its items stay "in use", because Rentalars
does not know which of them are back. A booked piece can no longer be
"unticked", and it does **not go out again in this project**: Rentalars
does not choose an item that has come back again, and "choose items" does
not offer it.

Every row shows how far along it is: "2 of 6 taken back", "2 not booked
yet" (ticked but not booked yet) or "taken back" when everything is back.
A row of which only **part** is back is highlighted in yellow and says
what is outstanding ("4 pieces are not back") – so you can see where you
are not finished yet. After a partial issue, rows that never went out
show "was not issued"; they don't need a tick.

**Finished by itself.** If, after booking, nothing is out any more and
nothing is still waiting for its issue or handover, the return of the
packing list is complete – you don't have to do anything else. The packing list
is then set to "returned", and the project goes to "Returned" as soon as
none of its packing lists is out any more (below).

**If something does not come back**, you note on the row what has
happened to it – "Cable defective, stays in the workshop", "forgotten at
the customer's, will be brought on Friday" – and press **"Note and close
the row"**. The field for this is open on partly taken-back rows; on all
others it opens under **"Does not come back?"**.

**Defect on return.** If you notice damage while unpacking, open
**"Report a defect of a returned item"** at the bottom: the **ID** of the
item (the list suggests the issued ones), "What is defective?" and, if you
like, a **photo** – on the phone the camera opens –, then "Report defect".
The item is set to "defective" straight away, the warehouse is notified,
the report is shown on the item with the note "Return of 2026-0042", and
 it becomes a service case like any other defect report
(section 4, "Report defect"). You can report any item of a product on
this packing list – even if it was not noted which of the twelve cables went
out.

**"Complete the return"** is below the list, with the question "Does
something not come back, or is the rest not issued any more?". You only
need it when the return does not finish by itself: when missing parts are
noted on their row, or when after a partial issue the rest no longer goes
out. It books whatever is still ticked and not booked, releases the
material of the packing list again and sets the project to **"Returned"** as
soon as none of its packing lists is out any more and none is still waiting
for its issue. After a partial issue, whatever never went out simply stays
in the warehouse – even if the project was never "Out"; Rentalars asks
first.

The list only turns red when you want to complete the return and
something is still missing: then Rentalars shows the rows that are still
open. Only when every row is ticked as back or has a note can the return
be completed.

Sold goods do not come back and are therefore not offered for ticking.

### The packing list of the whole project

Every subproject (section 7) has its own packing lists and is packed, issued
and taken back on its own. So that you can switch quickly, the packing list of
every subproject and of the whole project shows **all parts as tabs**
above the list, in order of their numbers: the whole project, every
subproject – the one currently open with one tab per packing list if it has
several – and finally **"All parts together"**. Subprojects whose packing list
you may not see are left out. "All parts together" opens the overview of
all packing lists (with the same tabs above it):

- **"By subproject"** – the whole project's own lines and every
  subproject with its progress: how much is packed, issued and back, plus
  the bar with its colours (above, "Packing"), what has been taken over
  from other subprojects and has already arrived, and what goes on to
  later ones.
- **"Summed up by article"** – this way the warehouse sees how much of
  each article leaves **the warehouse** in total. What moves on between
  the subprojects is listed separately under **"Taken over"** and is not
  counted twice.

The overview is **read-only**: packing, issuing, handing over and taking
back are done on the packing list of the subproject concerned. Subprojects
whose packing list you may not see are left out; the page says how many. Both
views are available as a **PDF**.

### Takeover and handover between subprojects

If a subproject takes over material from an earlier one (section 7,
"Material that moves on: takeover"), both packing lists show the pieces:

- in the **earlier** subproject, on the row, "6 go on to 2026-0042-2
  Bühne Schlosspark" – you pack and issue these pieces quite normally;
- in the **later** one, "Taken over from 2026-0042-1 Bühne Marktplatz, not
  from the warehouse". This row is not packed in the warehouse there and
  not issued; it counts neither towards progress nor towards weight.

**When the pieces arrive**, you book **"Book the handover"** on the row on
the packing list of the later subproject – in parts as well, preset with
everything still expected. You can only hand over once the material of
the earlier subproject has been issued. For the earlier subproject, the
pieces then count as **back**, for the later one as **issued**: its
packing list is then "out", the subproject as well as soon as its material
from the warehouse has also been issued, and the pieces come back to the
warehouse with it later. If the earlier subproject issued particular items
and all of them go on, they move along with it – their history then shows
both subprojects. For the handover you must be **allowed to edit both
packing lists**.

**A handover booked by mistake** is taken back on the row with "take
back" – the last booking first, and only as long as neither of the two
subprojects has been booked back and none of the pieces is already back in
the warehouse or has moved on.

**Pieces that are still waiting for their handover are missing from the
earlier subproject.** "Everything is back" leaves them out, and its return
can only be completed once they have been handed over, booked back after
all or noted on the row; the message names the subproject they are waiting
for. After the return of the earlier subproject, nothing more can be
handed over from there. Subrented pieces do not move along: only pieces
from your own stock are handed over.

---

## 11. Documents

*The "Documents" tab – right after the price overview – is for everyone who
can see the planning of a project. Anyone who may edit the project may
make documents; offers, order confirmations and invoices only those who
may also see prices.*

The tab contains all the paperwork that belongs to the project: at the top
the **documents made**, next to them the box **"Make a document"**, and
below them the **files** of the project with "Upload file" (below, "Files
of the project"). You can also reach the box with the "Make …" button in
the head of the project, which suggests the next document (section 7, "The
head of a project").

Rentalars writes the documents of a project itself – as a PDF, with your
logo, your address, bank details and registration details from the
company data (section 16):

| Document | What it contains | Number, by default |
|---|---|---|
| **Offer** | the lines with prices as in the order confirmation – or just the groups with their totals –, optional and alternative groups and lines marked; plus "Valid until" | `AN-2026-0001` |
| **Order confirmation** | the lines with prices, as agreed: groups with subtotals, personnel, logistics, surcharges, tax, total | `AB-2026-0001` |
| **Delivery note** | what goes to the customer: quantity, unit, article number, description, after the issue also the IDs of the issued items – without prices; with the fields "Delivered by, date" and "Received by, date, signature" | `LS-2026-0001` |
| **Invoice** | like the order confirmation, but without optional groups and without optional or alternative lines; plus "Due on"; with an **XRechnung** as a second file – only as long as "Use Rentalars as accounting software" is on (below) | `RE-2026-0001` |
| **Cancellation** | cancels an invoice, with negated amounts | from the same range as the invoices |
| **Crew disposition** | who works when, where and in which job function | `CD-2026-0001` |

**Language.** The fixed texts of the documents – column names, total
lines, units, dates and amounts – follow your company's "language of
documents", not the language of whoever creates them (section 16,
"Company data and settings"); in English, dates appear as 16/10/2026.
What you wrote yourselves stays as it is: the heading, introduction and
closing text from the document templates (below, "Templates and text
blocks"), text blocks, line texts and product names. If you switch to
English, the page "Template texts in English or German" takes
over the supplied texts of the templates (below, "Templates and text
blocks"); your own texts, text blocks and product names you translate
yourselves. An installation set up in English starts with English
templates ("Quotation", "Invoice" …). The XRechnung keeps its codes in
every language.

**Who sees what.** Offer, order confirmation, invoice and cancellation
show prices; only those who may see prices can see them. Delivery note and
crew disposition are visible to everyone who sees the tab – including the
warehouse. Anyone who is only planned in the project does not see the tab.

### Making a document

The **Documents** tab in the project, on the right **"Make a document"** –
or directly via the button in the head of the project, in which case the
kind is already chosen:

1. Choose the kind under **"Document"**. The offer is at the very top.
2. For the offer:
   - **"Level of detail"** – **"with positions"** (as before) or **"only
     groups"**. With "only groups", every group appears in the offer with
     its description and its total, without the lines in it; subgroups
     are indented with their own total, and the group above them ends
     with "Subtotal … with subgroups". A discount or flat price of the
     group is shown as a note below it. Lines without a group, the
     personnel, the logistics and the surcharges are still listed
     individually, as are
     optional and alternative lines of a group – they are not part of its
     total. The lines are numbered consecutively from 1. Net, tax and
     gross are the same in both cases. For the offer of a whole project
     this applies to the groups of each subproject; the blocks of the
     subprojects with their total remain.
   - **"Valid until"** and **"Validity in days"** – enter one of the two
     and the other changes along with it straight away (counted from
     today, the date of the offer). The suggestion is the validity from
     the offer's template (below, "Templates and text blocks"; initially
     14 days).

   For the delivery note, if the project has several packing lists: under
   **"Packing list"** a particular one or "all packing lists".
3. Under **"Text blocks"**, tick what should be included – your rental
   terms, for example (see below). Only the blocks meant for the chosen
   kind of document are offered; if you change the kind, the list changes
   along with it.
4. **"Draft as PDF"** shows the document as it would turn out – with
   "DRAFT" instead of a number. A draft uses up no number and is not
   saved; look at it as often as you like.
5. **"Make document"** – after a confirmation question, the document gets
   its number and from now on stays with the project.

What goes into the document, Rentalars takes from the project as it is at
that moment: lines and prices from the planning, the address from the
billing or delivery address (section 6), plus customer number, the
customer's VAT ID, project number, venue and contact person. As the
**date of service**, offer, order confirmation and invoice show the rental
period ("material out") – the rental days are counted over it. **Optional
groups** appear in the offer and order confirmation with the remark
"optional, not included in the total", with their total below; **optional
and alternative lines** appear there with "(optional)" or "(alternative)"
and "not included in the total", their totals below the gross total. In
the invoice both are left out completely, and the lines are numbered
without them. Subrentals that only cover a shortage do not appear – the
customer pays for the line they cover. **Customer material** appears in
the offer and order confirmation in its place, with quantity, without
price and amount and with "Customer's own material – taken along, not
charged"; in the delivery note with "Customer's own material – taken
along". Invoice and XRechnung leave it out (section 5, "Customer
material").
After the issue, the delivery note shows the issued quantities, before it
the planned ones – so it is best to make it after issuing.

**Offers.** A project can have any number of offers – a new one after each
change by the customer, with a new number. In the list, below the date it
says "valid until …" and, if it was made that way, "only groups". There is
no XRechnung for an offer. In the offer and the order confirmation, an
alternative names the line it could replace ("alternative to pos. 3"); an
alternative group is described as "alternative to “Licht Variante A”, not
included in the total".

**The look of the PDF**. Offer, order confirmation and invoice
are laid out more clearly; the amounts are the same as before.

- At the top level the document is divided into **Material**, **Personnel**,
  **Logistics** and – if there are any – **Surcharges**, each with a
  heading and, after its lines, a sum row ("Total Material", "Total
  Personnel" …). Under Material come the groups, with their subgroups and lines
  as in the planning, and the lines without a group; a project that has no
  groups at all gets its lines straight under "Material".
- The column **"Discount"** is printed only if at least one line has a
  discount; otherwise the table is narrower and the other columns have more
  room.
- Quantity, unit price, discount and amount stand **right-aligned under their
  headings**, so that the figures can be read straight down.

Documents that were made before keep the look they were made with
(above, "Filed unchangeably"); the new layout applies to documents made from
now on and to drafts.

**What isn't possible:** an offer, order confirmation or invoice for an
internal project (it has no customer) or for a subproject (they are made
on the whole project, below), a crew disposition for a project in which
nobody is planned yet, and a second valid invoice (below). Rentalars then
says what is missing and assigns no number.

### Whole project and subprojects

**Billing is done on the whole project** (section 7, "Subprojects"): make
the offer, order confirmation and invoice in the "Documents" tab of the
whole project. That way the customer gets one offer and one invoice for
the entire production:

- first the **shared lines** of the whole project (e.g. central power
  supply), without a heading of their own;
- then every **subproject that is not cancelled** as a block of its own:
  with the heading "Subproject 2026-0042-1 Bühne Marktplatz,
  10/03–12/03/2027", below it "Venue: …", its groups and its subtotal. A
  subproject with nothing to charge is left out;
- the lines are **numbered consecutively**; taxes and total apply to
  everything together, in the XRechnung as well. The date of service is
  the period from the earliest start to the latest end of all parts in it.

**Taken-over material** is charged only once – where it comes from – and
therefore does not appear a second time in the offer and invoice.

**In the "Documents" tab of a subproject** you make delivery notes – to
its delivery address, with its material – and crew dispositions. It does
not offer offers, order confirmations or invoices; it says that they are
made on the whole project and takes you there. A delivery note of the
whole project contains only its own material; there is no joint delivery
note for all subprojects. Taken-over material appears on the delivery note
of the subproject that takes it over with "Taken over from 2026-0042-1
Bühne Marktplatz".

**If you may not read a subproject**, you can neither make the price
documents of the whole project nor view them as a draft – they contain
every subproject; the message names it. Ask someone who may read all the
subprojects.

### Filed unchangeably

A document once made **never changes again** and **cannot be deleted**.
Rentalars files the PDF together with its content and a checksum; the
checksum proves that the file is still the one that was made. If the
planning changes afterwards, the document stays as it was.

The list **"Documents of the project"** shows every document with number,
date (for invoices also "due"), gross amount, and when it was sent to
whom. Clicking the name opens the PDF.

If an offer, order confirmation, delivery note or crew disposition is no
longer right, you make a new one – with a new number; the old one stays in
the list. With an invoice it isn't that simple: see "Cancelling".

### Invoice and XRechnung

**One** invoice applies per project (or, a final invoice with
advances, see "Advance, partial and final invoices" below). It contains what is in the planning
and is charged: lines with rental days and discounts, discounts and flat
prices of the groups, the personnel with hours or – with "per day" – with
days (unit "day"), hours above a daily limit with the remark "of which
2 h beyond 10 h a day at €55.00" (section 12), surcharges for night,
Sundays and holidays within the amount of the crew line with the remark
"incl. surcharges €126.00: Night 25 % on 4 h €45.00, …" – offer and
order confirmation likewise –, the section **"Logistics"** with
one line per vehicle booking – quantity in km, days or flat rates, below it
per trip the kilometres and rate ("12/06 To the setup: 84 km at €0.85
(incl. trailer surcharge €0.20)") or the days with the factor of the
rental scale; a booking without trip and amount is left out –, the
surcharges, the tax per kind of tax and the gross amount – but not
optional groups or optional or alternative lines. Offer and order
confirmation show the logistics as well. In addition:

- **Date of service** – the period "material out";
- **Payment terms** – those of the customer, otherwise those from the
  company data (14 days by default); from these, **"Due on"**.

If you bill personnel **by effort** (section 12) – the
default for new crew lines –, approve the times beforehand – otherwise the
planned number of hours appears on the invoice, marked as an "estimate".

**XRechnung.** With every invoice a second file is created: the electronic
invoice in the **XRechnung** format (UBL, according to EN 16931). In
business between companies in Germany, everyone has had to be able to
receive such invoices since 2025; over the next few years they will also
have to send them. The "XRechnung" link is next to the invoice in the
list.

**Invoices to public authorities** need the authority's **Leitweg-ID** in
the XRechnung. Enter it on the customer under "Leitweg-ID or buyer
reference" (section 6); Rentalars puts it as the buyer reference into
every XRechnung to this customer. If another customer requires an order
number or reference of their own, it belongs in the same field. If it is
empty, the project number goes there.

The XRechnung needs a few details that are otherwise often missing. Before
a number is assigned, Rentalars checks them and says what is missing ("For
the electronic invoice, this is missing: e-mail address of the
company."):

- company name and address of the company,
- e-mail address and phone number of the company,
- VAT ID or tax number of the company (all under Settings →
  Company data and settings),
- the customer's billing address.

A cancellation shows the company data as it is on the day of the
cancellation; if anything is missing then, Rentalars says so in the same
way before a number is assigned.

**The monthly invoice of the service cases**. A customer's
service cases of a month can be billed in one invoice (section 7, "Monthly
statement"). It has a section per case with title, activity and lines, is
numbered, filed as PDF and XRechnung and handed over to Lexware Office like
any invoice. It belongs to the case with the lowest number; it is sent from
that case. In the "Documents" tab of the other cases it is listed with
"monthly invoice of the service cases, belongs to …". If it is cancelled,
the statement becomes a draft again and its cases are open again.

### Advance, partial and final invoices

A project may have several invoices if they are of different
kinds. In the form "Make a document" an invoice has the field **"What the
invoice bills"**:

- **The whole project in one invoice** – as before. It is possible only as
  long as the project has no valid advance or partial invoice.
- **Advance invoice (payment on account)** and **Partial invoice** – they bill
  an **amount**, not single lines: give the **net amount** or a **percentage
  of the net total** (only one of the two) and, if you like, a text under
  "What is it for?" that stands on the invoice ("Anzahlung bei Auftrag").
  The invoice shows one line with the amount and the tax in the shares of
  the project. It gets the next number from the invoice range and is called
  "1. advance invoice", "2. partial invoice" and so on.
- **Final invoice** – it shows the **whole project** and below it deducts the
  advance and partial invoices already issued ("Less 1. advance invoice
  RE-2026-0007 of 12/10/2026", net and tax). The **amount to pay** is the
  rest. It needs at least one valid advance or partial invoice, and the rest
  must not be negative.

**The billing status.** As soon as a project has advance or partial invoices
or partial credit notes, the box **"Billing status"** stands above the list
in the tab "Documents": project net, billed on account (net), **still to
bill** (net and gross) and, per invoice, net, gross and its credit notes. So
you always see what is still open. While nothing is billed by a final
invoice, it is preselected in the form.

**Protection against double billing.** Rentalars refuses (and says why) if
- advance and partial invoices together would bill more than the project
  net (the rest shows what is still possible),
- an ordinary invoice is to be made although a valid advance or partial
  invoice exists (make the final invoice first),
- a final invoice is to be made without any advance or partial invoice,
- an advance or partial invoice is to be cancelled or credited although a
  valid final invoice deducts it (cancel the final invoice first).

Advance, partial and final invoices exist only for the **whole project**, not
for parts of a project and not for service cases. The project list does not
yet report a project with only an advance invoice as "invoiced".

**The electronic invoice.** The XRechnung gives an advance or partial invoice
the type code 326 (partial invoice) and a final invoice the type code 380;
the deducted invoices are listed as invoice references (BG-3), the deduction
as the prepaid amount (BT-113) and the rest as the amount due. The XRechnung
is built by us only and **not** validated against the KoSIT rules; Rentalars checks it against its own core checks (see "Payments, open items, the EÜR and
the archive").

**DATEV and Lexware.** An advance or partial invoice is booked as an invoice.
The final invoice books only the **rest** after the deduction (revenue net
and tax in the shares of the rest), because the advances are booked already.

**Sums and lists.** In the list of documents, in the sums of the outgoing
documents and in the API (`net_total`, `gross_total`), a final invoice shows
what it **adds** – the project minus the advances, i.e. the amount payable. The
advances count with their own invoices, so nothing is counted twice. The tax of
every advance and partial invoice is its net times the rate, rounded to the
cent; the rest on the final invoice balances the deviations.

### Cancelling

If an invoice is wrong, it is not changed but **cancelled** – that is what
tax law requires:

1. In the list, next to the invoice, **"cancel"** and confirm the
   question.
2. Rentalars makes a **cancellation**: the same lines with negated
   amounts, with the sentence "Cancels invoice RE-2026-0007 of
   12/10/2026." and also with an XRechnung. It gets the next number from
   the invoice range.
3. The invoice is now shown in grey with "cancelled" in the list, the
   cancellation with "cancels RE-2026-0007". Both stay with the project.
4. Now a new, correct invoice can be made.

As long as an invoice of the project is valid, Rentalars refuses a second
one ("Invoice RE-2026-0007 of this project is still valid. Cancel it
first.") – except advance, partial and final invoices (see above).

**Partial credit note.** A valid invoice need not be cancelled as a whole if
only a part is wrong: in the list next to it **"credit in part"** opens a
small form – **net amount** or **percentage** of what the invoice still
bills, and a text "What is it for?"; the button is called "Make credit
note". Rentalars makes a **credit note** with negative amounts ("Credit note
for invoice RE-2026-0007 of 12/10/2026"), numbered from the invoice range,
with an XRechnung (type code 384). The invoice stays valid; in the list the
credit note shows "credits RE-…", and in the billing status it is listed with
the invoice. More than the rest of the invoice cannot be credited. If you
cancel the invoice later after all, Rentalars cancels only the **rest** (net
minus earlier partial credit notes). If you credit **everything** that is left (100 percent or the whole rest), the
credit note is the **cancellation**: the invoice counts as cancelled and the
project can be billed anew. If a final invoice has a tax rate that the
advances push below zero, the tax of the cancellation can deviate by cents
from rule BR-CO-17; in return, invoice, credit notes and cancellation add up
to exactly zero. A partial credit note cannot be changed either, only
balanced by another invoice.

### Invoices in another program

If you write your invoices in your accounting software or another
program, untick **"Use Rentalars as accounting software"** under Settings →
Company data and settings (it is ticked initially; it has its own
box **"Bookkeeping and accounting"** on that page). Then

- Rentalars offers neither invoice nor cancellation – not in the box "Make
  a document", not in the head of a project, not via the interface –, and
  the head does not suggest an invoice even for a project that is back in
  the warehouse;
- under Settings → Accounting, handing over to Lexware Office and
  the DATEV export are hidden; the page says "Invoices are switched off";
- in the menu **Accounting** all tabs about bookkeeping disappear:
  **Capture a document** and **Incoming documents**, **Open invoices**, **Bank**,
  **EÜR** and **Archive**, **Asset register** and **Sales from stock**, and **Import old
  projects**. The places that lead there are gone too: the card "Asset accounting" of
  an item, the question "Record as an incoming invoice too?" after a purchase and
  the entry "Incoming invoices" in the settings. If somebody opens such an address
  anyway (an old bookmark), they land on the start page with the hint that no
  bookkeeping is done in Rentalars; the interface answers with the error
  `accounting_disabled`. **Outgoing documents** (offers, order confirmations,
  delivery notes and invoices made earlier) and the **monthly statement** stay; if
  somebody has rights only for the hidden tabs, the menu entry "Accounting" disappears
  altogether. Nothing is deleted: tick the box again and everything is there;
- invoices made earlier stay readable on the project and can still be
  sent; they can no longer be cancelled or handed to Lexware Office.

Offer, order confirmation, delivery note and crew disposition stay as they
are. The monthly statement of the service cases then shows the values to
copy into your program and marks the cases as invoiced (section 7,
"Monthly statement"). You close a project without an invoice – that has always been
possible. That the invoice has been written in the other program you note
 with the tick box **"Invoice issued"** in the head of the
project (below). If you tick "Use Rentalars as accounting software" again,
everything is as before.

### Invoices still to be written

Rentalars reminds you when a closed project has no invoice
yet.

**When a project counts as invoiced.** This concerns whole projects with a
customer – not internal ones, not subprojects (their whole project bills
them) and not cancelled ones. Such a project is invoiced

- if Rentalars writes the invoices: as soon as it has an invoice that is
  not cancelled;
- if you write them in another program (above): as soon as the tick box
  **"Invoice issued"** is ticked in the head of the project.

If a project is never invoiced – it was free of charge, or it is billed
with another project –, mark it with **"No invoice needed"**; then
Rentalars no longer reminds you of it. **"Undo"** removes the mark again.

**In the head of the project** – from "Returned" on, before that on the
"Documents" tab – you see where the invoice stands: **"Invoice
RE-2026-0007"** with its date, **"Invoice issued"**, **"No invoice"** or
**"Invoice open"**, yellow once the project is closed. Next to it are the
tick box "Invoice issued" (if the invoices are made in another program)
and "No invoice needed" or "Undo". Whoever may see prices sees it; whoever
may also edit the project changes it – even once the project is closed.
If a monthly invoice bills a service case (section 7, "Monthly
statement"), the head of the case names its number only to
whoever may open it – that is, may read its project and every case it
bills; everybody else sees "Invoice issued".

**The reminder** comes as the notification "Invoice still to be written"
(section 15) to the project manager and to the person named under "Also
remind" in Settings → Notifications – to both only if they may see
prices. With invoices made in Rentalars a click leads to "Make invoice" on
the "Documents" tab, otherwise to the project with the tick box. When and
how often it reminds you is set under Settings → Notifications in the box
"Invoices" – by default at 9:00, the first time one day after the project
was closed, then every seven days until the invoice is there (section 16,
"Notifications of the company"). Rentalars only reminds you of projects
whose net total is above €0. If a project
is reopened and closed again, the reminders start anew. With **"Service
cases too"** (on by default) Rentalars also reminds you of
done service cases with a
customer that have something to charge – times or expenses booked on the
case and not rejected –, of those done after the box was
switched on (section 16, "Notifications of the company"). A service case also counts as invoiced
if a monthly invoice bills it or a monthly statement has marked it as
invoiced (section 7, "Monthly statement").

**Older closed projects** are not followed: Rentalars does
not know whether their invoice was written. They do not show as "Invoice
open" in the list, the filter or the head; an invoice made in Rentalars
still shows. If such a project is reopened, it counts like any other from
then on.

**For an overview** there are the box **"Invoices still to be written"**
on the start page (section 2) and the project list: the filter
**"Invoice"** with "closed, invoice open" shows all closed projects
without an invoice, and the column **"Invoice"** (under "Columns") names
the number of the invoice for every project, "Invoice issued", "No
invoice" or "Invoice open".

Other programs read and set the state through the interface (section 16,
"API tokens").

### Crew disposition

The deployment plan for everyone working on the project: for each
deployment **Day**, **From**, **Until**, **Person**, **Job function**,
**Meeting point** (otherwise the venue) and **Contact**. Open places are
listed as "open". If someone travels with a vehicle of the logistics, it is named below the job function, for the driver with "driver"
(section 7, "Logistics").

Phone and e-mail appear only for people who have released them for
colleagues (section 12, "My area") – the PDF says so itself. **Hourly and
day rates and flat rates never appear in it.**

If you just need a quick printout for the crew, without a number and
without it being filed, use the **deployment overview**: "Print / PDF" in
the "Overview" tab (section 12, "The overview – what the crew sees").

### Sending

**"Send"** next to a document opens "Write mail" in the project, with the
document attached – for an invoice also with the XRechnung. The recipient
is prefilled with the contact person of the project, and the subject
carries the project tag (section 14). After sending, the list shows when
and to whom the document went, and the history of the project records it.

The documents can also be attached to any other mail from the project:
under "Documents" they are listed next to packing list, price overview and
deployment overview. Anyone with the special right "Write and send
correspondence" may send; a mailbox for the outgoing mail of the
correspondence must be set up (section 14, "Setting up mailboxes").

### Handing over to Lexware Office

If you keep your books in Lexware Office and handing over is switched on
under Settings → Accounting (section 16), every invoice and
cancellation in the "Documents" tab shows whether it is already in
Lexware Office:

- **"Hand to Lexware Office"** hands it over – as a **voucher** with the
  Rentalars number, the amounts per tax rate and the PDF; no second
  invoice number is created there. This runs in the background; you get
  a message when it is done, and the invoice then shows **"In Lexware
  Office since …"**.
- If **"hand over at once"** is set, every new invoice and cancellation
  goes across as soon as it is made. If that fails, whoever made it gets a
  message; the invoice itself is made all the same.
- **"Not handed to Lexware Office: …"** gives the reason if something went
  wrong; **"Hand over again"** tries once more and only does what is still
  missing.

Rentalars looks for the **customer** in Lexware Office by the customer
number; if the customer does not exist there, Rentalars creates them. If
the customer number in Lexware Office belongs to a different name, the
handover stops and says so. If they really are different customers, you
hand over with **"Hand over as new contact"**; Lexware Office then gives
the new contact a number of its own. An invoice is never handed over
twice.

Anyone who may make the invoice (edit the project and see prices) or who
may change the settings and see prices may hand it over.

### Product descriptions in documents

Whether the **description of the products** is printed under each line is
your choice: as a setting of the template (Settings → Document
templates, "Print product descriptions", default off – as before) and with a
tick box when creating a document, which is preset from the template's
setting and saved with the document. It applies to PDF, preview, mail
attachment, collective invoices of service cases and the XRechnung (BT-154).
The text a line carries itself always stays.

### Outgoing documents without a project

An offer or an invoice without a project – for a sale, a service, an
additional charge – you create under **Accounting → Outgoing
documents → "New outgoing document"**. The dialog asks for kind (offer or
invoice), customer, billing address, contact, date, payment term or
validity, subject and the choice of descriptions. Then the **draft** opens
on a page of its own: free lines, lines from products (no services, no
vehicles), text lines, discount, order and texts; a draft has no number and
can be deleted. **"Issue"** turns it into a document as in a project: the
same gapless number, tax rows, due date, XRechnung, DATEV, Lexware Office,
PDF and mail with attachment; immutable, corrected by a cancellation invoice.
The list shows "without project" in the Project column and filters by
**"Origin"**; the customer page shows the customer's documents (drafts, the
last ten, a link to all). A document without a project does not count in
profitability or in the payment reminders of projects. For an anonymised or
deactivated customer there is no new document; open drafts of an anonymised
customer are dropped. Whoever may see prices and read all projects may see
it; creating and changing additionally needs the right to edit projects.
Mails need an outgoing mailbox (default sender). Webhooks carry `project:
null` for these documents. Not built: the template's
free introduction text does not count in the comparison with the standard
texts.

### Outgoing documents

The sidebar has the menu entry **Accounting**, between
Material management and Customers, with the tabs **"Outgoing documents"**
and **"Monthly statement"** (section 7, "Monthly statement"). There are four more, each for whoever has the rights it needs: **"Incoming
invoices"**, **"Asset register"** and **"Sales from stock"** (both for
whoever may see purchase prices and read the material; section 4) and
**"Import old projects"** (for whoever may make documents of all projects;
below).
**Accounting → Outgoing documents** lists every document a customer got –
offers, order confirmations, delivery notes, invoices and cancellation
invoices, across all projects and service cases; crew dispositions go to
the crew and are not listed here.

The table is a list like any other (section 2, "Lists"). By default it
shows number, kind, date, project, customer, net, tax, gross and status;
via "Columns" you add title, month, recipient, due on, sent, Lexware
Office, monthly statement and "Created by". Every column can be sorted and
grouped, and the list downloaded as CSV. The amounts are those stored with
the document – Rentalars never recalculates them. The number opens the
PDF, the project its "Documents" tab. Under "Filter" you narrow it down by
kind – also "Invoices and cancellations" or "Monthly invoices of service
cases" –, status (sent, not sent, cancelled, not cancelled), Lexware
Office (handed over, failed, not handed over), customer, period with From
and Until, and with the search for number, project or customer.

Below the table are the **"Sums of the filtered documents"** – of all
documents of the filter, not only of this page: per kind the count, net,
tax and gross, and **"Invoices and cancellations together"**;
cancellation invoices count negative. So you see, for example, the
turnover of a month: kind "Invoices and cancellations", choose the period,
done.

The outgoing documents are there for whoever may see prices and read
every project – as the reports are. Whoever may read the settings finds
the button **"DATEV export and Lexware Office"** at the top: the DATEV
export and the handover to Lexware Office stay under Settings → Accounting
(section 16). The interface offers the same list with its sums (section
16, "API tokens").

### Incoming invoices

The invoices your suppliers send you – for cables, spotlights, a new truck –
are collected in **Accounting**. These are two tabs:
**Capture a document** (where you upload an invoice) and **Incoming documents**
(the register): with the file, the amounts, the freight spread over the goods
and, if you like, the items made of them. For whoever may see **purchase prices** and read the
material; uploading, correcting and booking in additionally needs the right to
edit the material, deleting the right to delete material. The settings are
in Settings (below).

**The list** (tab **Incoming documents**) shows number, supplier, dates, net, tax, gross, currency, status,
note, how the invoice was read, the file and who uploaded it, and lets you
choose the columns, sort, group and download as CSV like any list (section 2,
"Lists"). Under "Filter" you narrow it down by **supplier**, **status**, the
period **From** and **Until** of the invoice date and a search for number,
supplier, note or the text of a position. Below the table is the box **"Sum of
the filtered invoices"**: count, net, tax and gross – of all invoices of the
filter; invoices in another currency are converted with their own exchange
rate. An invoice in another currency without an **exchange rate** or an invoice
without **totals** is missing from the sums: the box then says "These sums are
incomplete." and how many invoices are missing – enter the rate or the totals.

**Uploading.** On the tab **Capture a document**, in the box **"Upload an invoice"**, choose a PDF, a picture
(PNG, JPEG, WEBP) or, an **e-invoice as XML** (see below) up to the size your administrator allows and click **"Upload
and read"**. Rentalars checks that the file is what its name says. It
reads the invoice at once:

- **Without AI** the text of a PDF with a text layer is searched for the
  **invoice number, the date and the due date, a supplier it already knows and
  the totals** (net, tax, gross). The positions you enter yourself.
- **With AI** – if "Reading invoices" is on under Settings → AI (section 16,
  "AI"), the same switch as for "Enter a purchase" – the AI also reads the
  **positions**, in the background; the page shows "The AI reads the invoice …"
  and reloads when it is done. Only the text of the invoice goes to the
  provider chosen there. A supplier that Rentalars does not know is only
  proposed, never created.
- A **scan or a photo** is stored, but **not read** – there is no text
  recognition. The page says "The invoice was not read"; you type everything.

Then the invoice's page opens and Rentalars asks **"Enter in the material
management too?"** – **Yes** leads to "Book in goods" (if there is no goods
position yet, the page says that it works as soon as the positions are read or
entered), **No** leaves the invoice as it is. The other way round: after
**"Enter a purchase"** (section 4) the page "Purchase entered" asks whether the
purchase should **also be recorded as an incoming invoice in the accounting** –
if an invoice file is attached to it. With **Yes** an incoming invoice is made
from that file: supplier, number and date come from the purchase, one line of the
Kontierung for each model and price, and the items are linked to it. You enter the
totals yourself. If the same file is in the register already, Rentalars opens that
invoice and makes nothing twice.

Whatever was read is marked ("read by AI – Check every value; the AI can be
wrong" or "read from the text"). Nothing is booked before you say so.

**The invoice's page.** Under "File" you see the original ("Open the
original", protected: only whoever may open the list gets it) and **"Read
again"**: empty fields are filled, typed values stay, and positions that are
not booked in are replaced by the new reading – a position that is booked in
is never touched. If the same file, or the same supplier with the same number,
is already there, a note says "This may be an invoice you have already:" with
links. Under "Invoice" you correct supplier (type and choose; a name that is not
in the master data can be created with **"Create the supplier"** – otherwise
Rentalars creates it when you book in), invoice number, invoice date, due date,
currency and exchange rate (for an invoice in another currency than the euro:
euros for one unit), net, tax and gross, the **status** and a **note**. Under
"Kontierung" Rentalars splits the invoice over **tax
accounts**, one line for each kind of cost:

- a line has a **description**, a **tax account**, a **kind** – **material**
  (goods), **ancillary cost** or **other** – the **net amount** (of the whole
  position, not a unit price) and the **tax rate**. Freight, packaging and
  customs you mark as "ancillary cost" – they are spread over the goods (below); a
  **discount** is an ancillary cost with a negative amount (only ancillary costs
  may be negative). "Other" – a service, a deposit – is only kept. A position
  that is booked in can no longer change its kind or amount, and cannot be
  removed.
- Only for **goods** the line asks **what it is treated as** (merchandise, low-value
  asset, fixed asset), and only for a **fixed asset** the **useful life (months)**
  – with a link to the AfA tables of the Federal Ministry of Finance, in which the
  tax authorities publish standard values. The **weight of one piece** is asked
  only if the ancillary costs are spread **by weight**.
- Article number, manufacturer and quantity are not asked; what reading
  found there stays with the line and is used when you book in – you choose the
  number of pieces there. If you change the net amount of a line, it keeps its
  quantity and the unit price follows.
- **The sum while you type.** Under the lines it says "The Kontierungen add up
  to … net", with tax and gross if every line with an amount has a tax rate, and
  the **difference to the net total** of the invoice. It changes with every value
  you type, without the page being loaded again; **"Save"** stores everything.
  "Another Kontierung" adds a line; at most 100 per invoice.
- **The tax account.** The accounts are master data (Settings → Master data →
  **Tax accounts**): number and name, and an account can be deactivated. Rentalars
  comes with a list for **SKR 03** that a company in event technology often
  needs (3400 goods received, 3100 external services, 4980 operating supplies,
  4985 tools and small equipment …). **It is a suggestion:** check the list with
  your tax adviser before booking by it; Rentalars books nothing and proposes no
  account, it only keeps what you choose. An account that is used on a line cannot
  be deleted.

**Ancillary costs and acquisition cost.** The ancillary costs of the invoice are
added up and spread over the goods. Under **"Ancillary costs are spread"** you
choose the **key** per invoice: **by value** (the default: the net amount of
each goods position), **by quantity** or **by weight**. A table shows per
position the quantity, the net amount, the **share of the ancillary costs**, the
**acquisition cost** and the cost **per piece**, and the sum. The shares are
cent-exact: they add up to the ancillary costs exactly, and an odd cent goes to
the first pieces. If you change the key, the table shows the new split at once;
it is stored with the invoice when you click "Save". A position that has been
booked in keeps the cost it got, even if you change the key later. Spreading by
weight needs a weight for every goods position.

**What each position is in the books.** Every goods position is merchandise, a
low-value asset (GWG) or a fixed asset (section 4, "Fixed assets, depreciation
and book value"). The **limit** of the settings (800 € net, inclusive, on the acquisition cost of
a piece – price plus its share of the ancillary costs) only **proposes**: a piece
up to it would be a low-value asset, a more expensive one a fixed asset. You have to **confirm** the kind by choosing it: if you leave it empty,
"Book in goods" refuses the position and names the proposal. A fixed asset
needs a useful life; merchandise is never guessed. This is a simplified standard setting,
no tax advice.

**E-invoices (XRechnung, ZUGFeRD).**

**Uploading e-invoices.** Under Accounting → Capture a document (and in the list of incoming invoices) you can upload **XML files** as well as PDFs and pictures: XRechnung (UBL or CII) and the XML form of ZUGFeRD / Factur-X. A **ZUGFeRD or Factur-X PDF** works too: Rentalars finds the XML embedded in the PDF itself.

**What happens.** An e-invoice is read *exactly* from its data – no AI, no text patterns: supplier (linked to a known supplier), invoice number, date, due date, currency, totals net/tax/gross and **all positions** with quantity, unit price, tax rate and article number. Discounts and surcharges of the whole document (freight, say) become positions of their own of the kind "ancillary cost" (discounts negative). You check and correct everything as with any incoming invoice; nothing is booked in before you say so.

**What you see.** Under "File" a note says *structured e-invoice* with the format (UBL / CII), the profile (XRechnung, ZUGFeRD / Factur-X MINIMUM, BASIC WL, BASIC, EN 16931, EXTENDED), specification, type code, the supplier's VAT ID and IBAN, buyer and order reference and the amount to pay. The **XML source** can be downloaded (for a ZUGFeRD PDF in addition to the PDF, which stays the original).

**When the file contradicts itself.** Rentalars compares the file with itself (sum of the positions against the total of the positions, positions with discounts and surcharges against net, net plus tax against gross; one cent of rounding is allowed). A difference is a **note**, not a refusal: the invoice is in the register all the same and you decide against the original.

**Credit notes.** A credit note (UBL CreditNote, type code 381) keeps the amounts as the file writes them and is marked "credit note". Its positions are of the kind "other": no goods can be booked in from a credit note.

**Files that cannot be read.** XML with a document type declaration (DTD) or entities is refused (XRechnung forbids them; nothing is loaded and nothing expands while reading), as is XML that is not UBL/CII or not well-formed. If the XML attached to a PDF is unusable, the PDF is kept and read as a PDF as before; a note gives the reason.

**Reading again.** "Read again" reads the XML again: empty fields are filled, positions you typed or corrected stay. A PDF uploaded before this version gets its XML this way (if it holds one).

**Limits.** Rentalars does *not* validate incoming e-invoices against the Schematron rules of EN 16931 / KoSIT; it reads them and compares the sums. It does not read invoices that come only as a picture or scan (as before).

**Booking in the goods.** As soon as the invoice has goods positions, **"Book in
goods"** appears in the head of its page. The booking page lists the goods positions. For each one
choose an existing **model** or type the name of a **new model**
(then its category is required, like in "Enter a purchase"), tick whether to
**book in this position**, enter the number of pieces (the default is what is
left; if you choose **more** than the quantity of the line, its net amount stays
and the unit price follows – three pieces of a line of 300 € cost 300 € together,
not 300 € each; if the amount does not divide by the number of pieces to four decimal places, the quantity of the line stays and the pieces share the amount to the cent), the storage location and serial numbers; for a new model "Keep as a
quantity (bulk material)" makes one row with the number of pieces instead of
single items. Check the kind and useful life, then **"Show the preview"**: it
lists exactly what would be made – position, model, pieces, net amount, share
of the ancillary costs, acquisition cost, per piece, kind and useful life –
and nothing has been written. Only when you tick **"Yes, book in exactly this"** and click
**"Book in"** are the items made. The booking uses the same checks as "Enter a
purchase": consecutive IDs, the supplier, the invoice number and date and the
invoice file at each item; customer material cannot be bought into; an invoice in
another currency needs its exchange rate. Everything or nothing is made.

- Each item gets its price, its **share of the ancillary costs**, the
  **acquisition cost**, the kind and useful life, the invoice date as its date of
  purchase and a link to the invoice and the position: on the item, the box
  "Purchase" says "From the incoming invoice – Position 2".
- A position that has been booked in is **not booked again** unless you tick
  **"Book in again"**; a position booked in part – 4 of 10 pieces – can be
  completed. When all goods positions are booked in, the invoice's status
  changes to **"booked in"** by itself.
- The statuses are **open**, **checked** and **booked in**; the buttons "Mark as
  checked", "Mark as booked in" and "Mark as open" set them by hand. They
  do not book anything.

**Deleting.** **"Delete the invoice"** removes the invoice with its positions and
its file – but only as long as nothing has been booked in from it ("Items were
booked in from this invoice: it cannot be deleted.").

**Settings → Incoming invoices** (module Administration; also by "Settings for
incoming invoices" at the top of the list): the **limit of a low-value asset
(GWG), net**, the **standard useful life (months)** and "Keep a memory value
of 1 €" (section 4). The files lie with the other stored files of Rentalars
and are included in the backup (section 16, "Backup and encryption").

**Not built:** Rentalars does not book by itself and proposes no tax account; the
accounts of the Kontierung prepare the exchange with the tax adviser. There is
no text recognition for scans.

### Payments, open items, the EÜR and the archive

*Payments are seen by whoever sees the list of outgoing documents (price right and all projects) and, for incoming invoices, the register; entering them needs the right to change there. The EÜR, the archive and the audit export need the settings (read) and both price rights – sale and purchase prices – because they add up the figures of the whole company.*

**Payments.** For every invoice – outgoing and incoming – you enter
**payments**: the day, the amount (gross, as it came into or left the account;
negative is a refund), the method and the purpose. The button **"Payments"** is
on the invoice (tab "Documents" of the project, the page of a free invoice, the
page of the incoming invoice). The rest is **worked out, never stored**: the
amount of the invoice (for a final invoice after the deduction of the advances),
less partial credit notes and cancellation, less the payments. The state is
"open", "partly paid", "paid", "overpaid", "cancelled" or "refund due".
**A payment is neither changed nor deleted:** a wrong one is **voided**, with a
reason; it stays in the list but no longer counts. Old invoices from the import
that counted as paid there count as paid without a payment being entered.
Payments are entered by hand or taken over from a bank statement (see
"Bank" below). For an
incoming invoice in a foreign currency the amount and the payment stand in the
currency of the invoice; the euros follow from the rate of the invoice.

**Open items** (a tab of Accounting) shows what customers still owe ("Customers
owe") and, for whoever may see purchase prices, what is still to be paid to
suppliers, the oldest due day first, with the sum and the overdue part, also as CSV.
There is the page **"Credit balances"** next to it: invoices that were
**overpaid** or **cancelled or credited** after payment (we owe the customer money) and
**credit notes of suppliers** that were not paid back yet (the supplier owes us money). You
enter the refund as a **negative payment** at the invoice; the line disappears then. Everybody
sees only the page they may see.

**Bank.** The tab **Bank** (seen by whoever has both price rights and may read all projects and the
material; changed by whoever may also edit projects everywhere and the material) reads in a **bank statement**: **CAMT.053** (XML) or the **CSV file** of
the bank (delimiter, character set and header row are recognised, lines before and after
are skipped; a line with a day but no readable amount refuses the file – a statement with a
missing line is worse than none). Of the file only the transactions stay – day, amount, counterparty, IBAN,
purpose – and its checksum; the same file is not read twice, and a transaction that an
earlier, overlapping statement had is not entered again. For every **open** transaction the
page shows the invoices it may belong to, by: **invoice number in the purpose** (the
strongest sign), **amount equal to what is still open**, and **name**. Money coming in fits
open outgoing invoices and credit notes of suppliers, money going out fits open incoming
invoices and refunds to customers – money going the wrong way is not booked. Very short or
purely numeric invoice numbers (a date, an amount) are not read from the purpose. **A suggestion books nothing:** only a click on **"Enter
payment"** creates the payment – with the same rules as by hand (no day in the future,
euros only) – and links it to the transaction. A transaction can be **set aside** with a
reason ("Set aside", for private matters or fees) and taken back. If you void the payment
at the invoice, the transaction is open again. Part payments are entered by hand at the
invoice; a transaction is always matched as a whole. The matching is an aid, **not a
reconciliation with the bank**: Rentalars does not fetch statements by itself, and foreign
currency is not matched. The API: `/accounting/bank/imports` and
`/accounting/bank/transactions`.

**Checking the e-invoice.** Rentalars checks every invoice it issues and every
e-invoice you receive against **its own core checks** of EN 16931 and the XRechnung
(mandatory fields, sums, tax categories, the Leitweg-ID …). The result stands on
the invoice ("meets the rules checked" or "n rules broken" with the number of the
rule) and can be repeated with "Check again". By default the check is **a finding,
not a block**: the invoice is issued all the same. Whoever does not want that
switches on **"Do not issue an invoice with errors"** in the settings. **It is no
replacement for a validator:** the schema and the Schematron rules of the KoSIT are
not part of it.

**ZUGFeRD / Factur-X.** In the settings you choose the **format of the invoice**:
**XRechnung** (the PDF and, apart, the XML file) or **ZUGFeRD / Factur-X** (one
PDF/A-3 with the invoice data inside). The format applies to invoices made from now
on; existing ones stay as they are. The checksum of the invoice is that of the stored
file. When sending, an XRechnung takes its XML file along if the customer has a buyer
reference (the Leitweg-ID of an authority); otherwise it can be added. A ZUGFeRD PDF
goes out alone, its data is inside.

**EÜR.** The tab **EÜR** works out the year on the **cash basis**: income is the
payments on outgoing invoices, split over the tax rates of the invoice, plus sales
from stock without an invoice on the day of the sale; expenses are the payments on
incoming invoices, split over the tax accounts of the positions. **What is booked in
as a fixed asset or low-value asset is not an expense but depreciation** (a
low-value asset completely in the year of acquisition, a fixed asset by the month
principle); at a sale the book value leaves as an expense. **Turnover tax** stands
apart: received, input tax paid, balance. The EÜR shows two figures: the **result without turnover tax** and the **surplus as the EÜR counts it** (with the turnover tax of the payments; the turnover tax still owed stands between them). Payments to a tax office within ten days of the turn of the year are reported as a hint: Rentalars does **not** apply the ten-day rule (§ 11 EStG), every payment counts on its day. If you sell a part of an asset kept as bulk material, the depreciation of earlier years stays as it was; the pieces sold depreciate until the day of the sale. An asset set to **lost** or **retired** stops depreciating from that day, and its book value goes into the EÜR as a disposal; if the change log no longer knows the day, Rentalars says so. Rentalars recognises payments to the tax office by the **supplier**: in the master data you mark
it as "tax office – turnover tax" or "tax office – income tax and other private taxes".
What is paid to a tax office for turnover tax is not an expense but is set against the
turnover tax ("Still owed to the tax office"); the other kind stands apart and does not
count as an operating expense. A refund is a negative payment. Trade tax is an expense like
any other; its supplier stays unmarked. Only whoever may see the EÜR sees and changes the mark (it decides the profit). For a **small business** (setting) everything counts gross. The page names
what is only approximated (sales without an invoice, foreign invoices without a rate,
goods above the limit of a low-value asset that are not booked in yet) and gives a
**CSV file** with every line behind the figures. **This prepares the figures for the
tax adviser; it is no tax advice and no filing.** Double-entry bookkeeping does not
exist; it is noted for later.

**Archive.** Every issued outgoing invoice (and every other document for customers) and
every incoming invoice goes into the **archive** at night: files with SHA-256 and size,
and the end of the **retention period** – the end of the calendar year plus eight
years for invoices and accounting vouchers, six for business letters (settings). At
night a part of the archive is checked against the checksums so that every file is
checked within the set number of days. A changed or missing file turns the **self-check**
red and reaches the operators. An archived incoming invoice cannot be deleted until the
period ends (a new upload for one more day); after the period the entry stays in the log
("deleted after the period"). Outgoing documents can never be deleted. The page
**Archive** shows the numbers, the findings and the list, and checks everything at once.
The maintenance changes nothing about payments: a payment cannot be changed
or deleted even in program code, only voided.

**Export for an audit and procedure documentation.** On the Archive page you download a
**ZIP export** (one year or all) – for a large archive with **"Make in the background"**:
the page shows the progress, the ZIP file is then under "Tasks", and only the person who
asked for it sees it: tables as CSV (outgoing documents, incoming invoices,
payments, the lines of the EÜR, the asset register, the archive log), a description
`index.xml` in the manner of the description standard, the vouchers themselves and
`SHA256SUMS`. The **procedure documentation** is a draft that Rentalars fills from the
settings (page, PDF, Markdown); the company completes the rest. **Rentalars is not
GoBD-certified, and `index.xml` has not been tested with an audit program** – discuss
both with your tax adviser.

### Importing old projects from invoices

You have written invoices for years before Rentalars – for projects that
should now be in it? You take them over from the invoices
themselves: **Accounting → Import old projects**, for whoever may see prices
and edit all projects. Each old invoice becomes a **closed project** with its
positions and a **historic invoice** with the original PDF – so that the
history of a customer is complete.

1. **Upload.** Choose up to 30 PDFs at a time (each at most 10 MB, 120 MB
   together) and click **"Upload and read"**. Only PDFs with text are read; a
   scan is not (no text recognition) – its data you type. A file that was
   imported before, or that is in the upload twice, is marked at once. The
   invoices are read **in the background**, one by one; the page shows them as
   they are ready.
2. **Reading.** With AI on for "Reading invoices" (Settings → AI) only the
   **text of each invoice** goes to the provider chosen there – nothing else.
   Without AI, or if it fails, Rentalars takes customer, invoice data and
   positions from the text by patterns; that works for simple invoices.
3. **Check.** (Each position also has a **description** – the
   further lines under the name, as on the invoice, which you may change – and
   a **kind**: **material**, **personnel** or **logistics**. Rentalars proposes
   the kind from text and unit (hours, "technician", "sound engineer" →
   personnel; kilometres, "transport", "delivery" → logistics; else material);
   change it and **save**, and Rentalars offers the matching **job function**
   (personnel), **vehicle** (logistics – a motor vehicle of the fleet) or
   **product** (material). Personnel becomes a personnel line without a person –
   by hours, by days (whole days) or as a flat rate – logistics a vehicle line
   with a trip of its own as a flat rate. Under **customer** the page says in one
   sentence what was found: an existing customer (same name and address, or a
   similar name at the same address), customers that may be meant, or "no existing
   customer matches – a new customer is created from the data of the invoice".
   Taking over creates a new customer only if you leave it so.) Each invoice is shown as a form: **"Take this invoice over"**,
   the customer ("Customer in Rentalars" – an existing one or a new one from
   the data of the invoice), invoice number and date, service period, name of
   the event, "The invoice was paid" with "Paid on", the project (**"A project of
   its own"** or joined to the project of another invoice of the batch, for
   two invoices of one event) and the positions with text, quantity,
   unit, unit price, discount, tax and – if you like – a **product** of yours
   (otherwise it becomes a free line). **Warnings** mark what looks wrong but
   does not stop you: the positions do not add up to the printed totals, the tax
   does not fit, quantity × price differs from the printed amount, the same number
   is in the upload twice. **Errors** stop that invoice until you correct them: no
   invoice number or date, a date in the future, a number that exists already, a
   number **inside the number range of the invoices you make in Rentalars** (the
   message suggests a number like "ALT-…" or moving the counter), a currency other
   than the euro, a tax rate that is not in your master data, no position with a
   price. **"Do not take over"** skips an invoice.
4. **Confirm.** **"Check and continue"** shows **exactly what will be created**:
   the customer (existing or "will be created"), the project, the positions,
   the invoices with date, net, gross and state ("paid" or "open"). Only
   **"Take over …"** creates it. You may confirm part of a batch.

**What you get:** per invoice a project **numbered ALT-year-number** (its own
counter, so your running project numbers stay as they are), closed, with the
positions as lines, and the invoice as an issued invoice with the number,
date and amounts of the old one and its PDF. The project's note says
"Imported from invoice … on … by …". **What does not happen:** no mail, no
task or notification, no reservation of material, no change to the
availability, no automation and no webhook; nothing is handed to Lexware
Office; the number ranges of your running documents stay untouched. The
historic invoice cannot be handed over to Lexware Office or cancelled, and it is
not in the list of Lexware errors. In the **DATEV export** (Settings → Accounting) it
appears only if you tick **"Include invoices taken over from an old system"**.

**Undo.** For **seven days**, as long as nothing was changed on the projects,
invoices and new customers – no document, mail, file or time added, no
change in the log –, the batch's page offers **"Undo this import"**; only who
imported it (or an administrator) can do it. PDFs that were uploaded but not taken
over are deleted after 14 days – but only when someone opens the
overview of the import or uploads a file; until then they stay on the
server.

**Limits:** scans (no text recognition), other currencies than the euro and
credit notes are not imported. **How good the AI reads real, foreign
invoices has not been tried enough** – have a few read first and check the
preview critically, line by line; it is a proposal.

### Templates and text blocks

**Document templates** (Settings → Document templates): for every
kind of document – the offer too – there is a template with **Heading**,
**Introduction**, **Closing text**, an **Additional footer** (it appears
below address, bank details and registration details) and the tick box
**"Print the logo"**. Templates are changed, not created or deleted.

The template of the **offer** also has the field **"Validity in days"**:
a new offer is valid for that many days unless you enter something else
when making it. The default is 14 days.

In the introduction and closing text, **placeholders** insert the data of
the project:

| Placeholder | becomes |
|---|---|
| `{project}` | the project number, e.g. 2026-0042 |
| `{project_name}` | the name of the project |
| `{customer}` | the name of the customer |
| `{period}` | the period "material out" – the date of service –, e.g. 12/06/2026 – 15/06/2026 |
| `{venue}` | the venue |
| `{due_date}` | the due date (invoice only) |
| `{payment_terms}` | the payment terms in days (invoice only) |
| `{valid_until}` | the "Valid until" date (offer only) |
| `{validity_days}` | the validity in days, e.g. 30 (offer only) |

Supplied for the invoice, for example, are this introduction and this
closing text (where the documents are in German, the German ones):

```
For the project {project} “{project_name}” ({period}) we invoice:

Please transfer the amount by {due_date}, quoting the invoice number.
```

And for the offer:

```
For the project {project} “{project_name}” from {period} we are pleased to offer the following. This offer is valid until {valid_until}.

We look forward to your order.
```

A placeholder that Rentalars does not know stays as it is written – so a
typo shows up in the draft.

**Template texts in English or German**. If you write to
your customers in English – or want to go back to German –, open the page
**"Template texts in English or German"** under Settings → "Documents and
accounting" (or above the list of document templates):

1. Choose **"English texts"** or **"German texts"** at the top.
2. For each template, heading, introduction and closing text are shown
   with **"Now"** and **"New"**; what is ticked is taken over. Fields
   marked **"own text"** – neither the German nor the English default
   text – are not ticked and stay unless you tick them. Footer, logo and
   the validity of the offer always stay.
3. The "Language of the documents" is a setting of its own (section 16,
   "Company data and settings"); with **"Also make the documents
   English"** or "… German" it changes along.
4. **"Take over the English template texts"** or "Take over the German
   template texts".

The change log keeps the previous texts. If somebody changed a text while
the page was open, theirs stays, and the page says so. Whoever may read
the settings may see the page; whoever may change them may take texts
over.

**Text blocks** (Settings → Text blocks) are paragraphs added when a
document is made: rental terms, liability notes, "Aufbau nur bei trockener
Witterung" (setup only in dry weather). Each one has a **Name**, the
**Text** (placeholders work here too), under **"For"** the kinds of
document for which it is offered (none ticked: all), and the tick box
**Active**. When making a document, you tick which ones go along; they
appear above the closing text. A cancellation never gets text blocks.

### Number ranges of the documents

Each kind of document counts on its own (Settings → Number ranges):
**Offers** (`AN-2026-0001`), **Order confirmations** (`AB-2026-0001`),
**Delivery notes** (`LS-2026-0001`), **Invoices and cancellations**
(`RE-2026-0001`) and **Crew dispositions** (`CD-2026-0001`), starting
afresh each year. Prefix, digits and next number can be changed as for the
other ranges (section 16).

Invoice numbers must be without gaps. That is why Rentalars assigns a
number only when the document is really made – never for a draft and
never when something is missing. Do not set the next invoice number back. A range that starts afresh each year keeps the
"next number" you enter in the middle of a year (say after a switch from another program);
only in the new year does it start at the first number again. The date of a document without a project lies in the
current year and not in the future; if you leave it empty, today applies.

### Files of the project

Below the documents, in the same tab, is the **"Files"** box: everything
else that belongs to the project – stage plans, riders, show files,
contracts, purchase orders, light plots; the same for a service case. With
**"Upload file"** in it you file a document. When doing so, you choose a
**Document type**; it determines whether the file is **visible to the
crew**. Stage plan, rider, running order and hall plan are, contract and
purchase order are not. This can be set differently per file (pencil).

**Documents of the suppliers** – offers, order confirmations, delivery
notes and invoices for subrentals – also appear here, with their kind and
a link "Subrental at …" to the supplier's page in this project; that is
where they are filed (section 9, "Subrenting"). You change their kind with
the pencil under "Kind of document"; they are not visible to the crew
unless you set it differently.

The usual document and image formats are allowed (PDF, Office and
OpenDocument files, images, text), ZIP archives, MVR files and, show files (just below), up to a size that is set in the
settings (50 MB by default; the form tells you). Rentalars does not accept
programs and scripts. Attachments of a mail land here with one click
(section 14), an MVR file automatically on import (section 7, "Importing
an MVR file").

**Show files.** The show of a lighting console, media server or sound
desk belongs to the project: whoever programs the next show finds the
latest version here, and the crew has it on site. With "Upload file" you
upload it like any other file. Rentalars recognises show files by their
extension – for example grandMA3 (`.show`), grandMA2 (`.show.gz`), ETC Eos
(`.esf`, `.esf3d`), Hog 4 and ChamSys MagicQ (`.shw`), Avolites Titan
(`.avo`), Resolume (`.avc`), WATCHOUT, QLab, Yamaha DM7 (`.dm7f`), DM3,
CL/QL and TF, Midas M32 and Behringer X32, DiGiCo (`.ses`), d&b R1
(`.dbpr`) and L-Acoustics LA Network Manager; exactly which extensions is
stated in the message when a file is not accepted. A show that is a
**folder** – disguise, dLive and many others – you pack as a **ZIP
file**.

A show file automatically gets the document type **"Show file"** (visible
to the crew) and, where the extension makes it unambiguous, the **"Console
or software"**; for `.shw` – Hog 4, MagicQ or M32 – you choose it
yourself. Enter the **"Software version"** the show was saved with. The
show file of a console uploaded last is its **"current show"**; earlier
ones of the same console stay as they are. With the pencil of the file you
change the console, the version and which one is the current show. In the
list and in the overview, below the name it says "Console · version …"
and, for the current one, "current show". For large shows with media, an
administrator can raise the "Largest file to upload (MB)" (section 16).

---

## 12. Personnel

*For everyone with access to "Personnel"; the part about your own profile
and the overview of a project is for everyone who gets planned.*

Two things that Rentalars keeps strictly apart:

| | Where from | Who sees it |
|---|---|---|
| **Price for the customer** | from the service product of the job function, e.g. `D-003` "Sound engineer" at €45.00 per hour | those who may see prices |
| **Costs for the company** | from the hourly or day rate of the person in this job function, e.g. €35.00 per hour, €280.00 per day – without a rate of their own, from the guide value of the job function | those who may see hourly rates and personnel costs – and the person themselves |

Both can be higher above a limit of hours per day (below, "What personnel
costs and earns").

The customer does not pay "Anna's hourly rate" but an hour of a sound
engineer. What Anna costs the company is none of the customer's business –
nor of everyone in the house.

### Job functions

**Personnel → Job functions.** A job function is *as what* someone is
planned: sound engineer, lighting technician, stagehand. A new
installation comes with eight – technician, lighting technician, sound
engineer, media technician, stagehand, warehouse, project planning and
other –; you can rename them, add to them, deactivate them.

**What the rate means** (note in the list and form): the rate of
a job function is the **hourly wage** or day cost of the planned staff – an
internal cost value, **not the price for the customer**. You change
customer prices under Material management → Products, on the function's
service product; the note links there (only with the right to read
products).

**Every job function has exactly one service product**, and every service
product belongs to exactly one job function – both with the same name, the
product in category D. Its price is what the customer pays for one hour of
this job function. If you create a job function ("New job function"), its
service product is created automatically when you save – unit hour,
billing by hours –; you enter the **"Price per hour for the customer
(net)"** right in the form (with the price right) or later on the product.
Conversely, the job function is created when you create a service under
Material management → Products (section 5, "Product kinds"). If you rename
one, the other follows, as long as both had the same name.

In the list of job functions, the service product leads to its page, as it
does on the page of a job function; there you change price, tax rate and
the limit in hours per day (below, "What personnel costs and earns"). If
it has no price yet, it says "no price yet", and crew lines of this job
function cost the customer €0.00 until you enter one. The
eight supplied job functions get the price and internal costs per hour
given in the first-run setup (€45.00 and €30.00 proposed, section 3); in
installations set up before, they came without a price.

For each job function, also:

- **Guide value for internal costs per hour** – so that the calculation
  can already work while a place is not filled yet or the person has no
  hourly rate of their own.
- **Guide value per hour from the limit** – the same for the hours of a
  day above the limit of the service product; if empty, the guide value
  per hour applies.
- **Guide value for internal costs per day** – the same for a whole day
  (billing "per day", section 12, "What personnel costs and earns"); it
  applies as long as a place is not filled or the person has no day rate
  of their own. The list of job functions shows it in the column "Guide
  value per day". Only those who may see personnel costs see the guide
  values.
- **Maximum discount in percent** – empty: no limit, 0: never discounted
  (section 8, "Discounts"). Only with the price right.

**Deleting.** "Delete job function" takes the service product with it. If
people have the job function or it has already been planned – also as a
material line with its product –, that isn't possible; deactivate it
instead. The product of a job function cannot be deleted on its own.

**Job functions from earlier times.** The update gave every job
function its own service product: a shared product stayed with the job function of the
same name (otherwise the oldest), the others got a copy with their name
and the same prices; a job function without a product got one with the
price of its most recent crew line billed by hours, otherwise €0.00. Go
through the prices in the list of job functions once.

**The job function is the precondition for planning.** Only people who
have at least one job function assigned are offered for planning – in the
selection of the crew lines and under "Who is free?". Pure office accounts
without a job function don't appear there; they still appear in the
personnel plan, as long as the tick box "Only people with deployments or
absences" is not ticked (section 15, "Personnel plan").

### People

**Personnel → New person.** First name, last name, kind (permanent
employee, temporary staff, freelancer), **Position in the company** – for
example "Head of lighting"; it also appears in the e-mail signature
(section 14) –, e-mail, phone, note. For freelancers also company,
address, tax number and VAT ID. Under "Login and colleagues" you decide
whether colleagues may see phone and e-mail (below, "My area"). There is also **"Distance home – company (km)"**: with it, Rentalars
deducts the way to work from the person's trips (section 13, "Expenses and
travel costs"); if empty, nothing is deducted. The distance is maintained
by whoever may edit personnel; it is part of the person's data export and
disappears on anonymisation.
You enter job functions – and, where needed, rates of their own – on the
person's page after "Save person".

**Every person has a login.** Personnel and users are one in Rentalars:
every person is at the same time an account they log in with – to see
their deployments, accept them, record times and keep their availability
up to date. And every account created under Settings → Users also
appears in personnel.

- When a new person is saved, Rentalars creates their account: with the
  role **Crew** (freelancers: **Freelancer**) and a username made from the
  name – `anna.becker`, or `anna.becker2` if that already exists. The
  account has no password yet; the person can only log in after the
  invitation or with a one-time password.
- **"Send the invitation by e-mail now"** (only when creating) sends the
  link right away with which the person chooses their own password. Later
  this is done under Settings → Users (section 16).
- The **e-mail address is optional.** Without it there is no invitation
  but a **one-time password**, which you give the person in person or on
  the phone (section 16, "Users"). An e-mail address belongs to exactly
  one person.
- First name, last name, e-mail address and "active" are shared by person
  and account: what you change in one place applies in both.
- **Roles and rights** stay under **Settings → Users**. Anyone who
  may do more than Crew – project management, warehouse, office – gets
  their role there.

On the person's page, under **"Login"**, you see the username and the
state: "no password yet – invite or set a one-time password", "password
set, not logged in yet" or "last login …". Those who may see the
settings get straight to the account via "Roles and access".

**Who may see what**. The list Personnel → People has – like
Settings → Users – three columns you show via "Columns": **"Finances"**
(prices, purchase prices, both or no), **"Personnel data"** (people,
hourly rates, both or no) and **"Customer data"** (read, change or no).
Rentalars computes them from the roles of the account: "Finances" from the
special rights "See prices and calculation" and "See purchase prices",
"Personnel data" from the module Personnel – the people with their
contact data – and the special right "See hourly rates and personnel
costs", "Customer data" from the module Customers. **"no access"** means:
the account cannot log in – it has no password yet, is deactivated or its
"valid until" has passed (also before the nightly job has
deactivated it; section 16, "Users"). The
columns can be sorted and grouped and go into the CSV file; a legend
below the list explains them. So, before a data subject request for
example, you see at a glance who can get at hourly rates or customer data.

**Job functions and rates.** On the person's page under **"Assign a job
function"**: choose the job function, "Save". Nothing more is needed –
Anna can now be planned as a sound engineer. **Hourly rate**, **Hourly
rate from the limit**, **Day rate** and **Valid from** are optional:

- Without a rate of their own, the **guide value** of the job function
  applies; the list shows it in grey with "(guide value)".
- The **hourly rate from the limit** prices the hours of a day above the
  limit of the service product (below, "What personnel costs and earns");
  if empty, the hourly rate applies ("as the hourly rate"). The person's
  page shows it in the column "From the limit".
- Without "Valid from", the rates apply **always**, from the beginning.
- A person can have several job functions, each with rates of its own –
  Anna as a sound engineer at €35.00 per hour and €280.00 per day, as a
  stagehand without a rate of her own.

Only with a job function can a person be planned. Anyone who may edit
personnel may assign job functions. Only those who may also see hourly
rates and personnel costs may see and change rates – the day rate is one
of them; without this right, "Assign a job function" has only the job
function field, and someone with the right enters the rates later.
"remove" takes a job function away from the person again; existing crew
lines and time entries remain. If the person has rates of their own in
this job function, only someone who may see the rates can remove it – they
go with it.

> **A rate changes.** Enter the new rates with the day from which they
> apply. The old ones stay for the time before ("All rates with their
> dates"). A row applies as a whole: if you leave the day rate empty in
> it, from that day the guide value applies again, not the old day rate.
> Lines in projects and time entries that already exist keep the rate
> they were created with – a rise in July changes no project from May.
> Rates without a date exist only once per job function; if you want to
> change them, you enter them anew there.

The page of a person has three tabs. **Person** also shows their login,
their **planned deployments**, their **absences**, their
**qualifications** and their **recorded times**; **Timeline** shows their
weeks, **Availability** their availability calendar – as a month or a
week – and their linked calendars (both below).

**Many people at once** – for example the list of freelancers from a
spreadsheet – you bring in with "Import" above the list of people (section
16, "Import and export"). They too get their login with the role Crew or
Freelancer.

**Deactivating, exporting, anonymising, deleting** (at the bottom of the
page, "Deactivate, privacy"). Someone who no longer works with you is
deactivated ("Deactivate person"): no longer plannable, no login any more,
everything recorded remains; "Reactivate person" brings them back. For a
request for information under the General Data Protection Regulation,
"Export all stored data" provides a file with everything stored about the
person. "Anonymise" permanently deletes name, contact data, notes,
absences, availability, calendar links and qualifications together with
their certificates, and closes the login; deployments and times remain
without a name so that old projects stay complete. An account with "has
all rights" cannot be anonymised – take that right away beforehand under
Settings → Users. **Deleting** ("Delete person") is only possible
for someone who has never logged in, was never planned and never recorded
a time; their account disappears with the person. Someone who has already
logged in is deactivated or anonymised. Your own account and the last
account that may manage the settings cannot be deactivated. For
customers there is the same export on the customer page. It contains the **AI
summaries** of the customer's projects (with their earlier versions) only if
you could read them on the project's page yourself – which needs the right to
read all messages, also those with a lock. How many it left out is stated in
it as `ai_summaries_withheld`.

### Qualifications and certificates

Driving licence, mobile elevating work platform, rigging, first aider,
safety instructions: what someone can do and has to prove is listed on the
person's page under **"Qualifications"**. "Add" asks for:

- **Qualification** – the type, from the list under Settings →
  Qualification types (section 16);
- **Details** – for example the driving licence classes: "B, BE, C1E";
- **Acquired on** and **Valid until**. If "Valid until" is left empty and
  the type says how long it is valid (a first-aid course two years),
  Rentalars works out the date from "Acquired on". Otherwise empty means:
  does not expire ("no expiry");
- **Certificate** – the PDF or image of the certificate. A new file
  replaces the stored one.

"Save qualification". The list shows the expiry date in green, in yellow
during the last 60 days before it, and in red once it has passed. If a
qualification is about to expire or has expired, that is also shown at the
top of the person's page ("Rigging until 30/11/2026", "First aider
expired").

**Driving licences.** A qualification type for a driving
licence names under **"Driving licence classes"** which classes it covers,
e.g. "B, BE" (section 16, "Master data"). By them the logistics checks
whether the driver of a vehicle has the class needed – only as a hint,
and only with a valid qualification (section 7, "Logistics").

**60 days before expiry**, personnel planning gets a notification
("Qualification expiring") – and so does the person. In good time to book
the schedule.

### The timeline of a person

The **"Timeline"** tab on every person shows their weeks at a glance:
**deployments** as bars (project and job function) in the colours of the
personnel plan – orange firm, yellow option, grey inquiry, paler with a
dashed stripe still requested, **filled red** a deployment in conflict
(section 15, "Personnel plan") –, below them the
**availability** – green, yellow and red as the person entered it, hatched
the busy times from their linked calendars, plus their absences – and when
a **qualification** expires. The legend is below. The same availability
applies as in the personnel plan: one at any point in time. That way you
see when someone is free before you ask. Period and navigation as
everywhere: "‹ earlier", "this week", "later ›", "From" and one to twelve
"Weeks". Projects you may not open appear only with their number.

### Absences and availability

**Absences** – holiday, sick, not available, with From and Until – you
enter on the person's page ("Enter absence"). Every person can also enter
their own absences themselves and keep their availability up to date in
their own calendar (below, "Availability calendar" and "My area").

**Personnel → Availability** answers the question "Who is free?": choose a
period and, if you like, a job function – "who is free on Saturday and can
do sound?". With a job function chosen, only the people who have it are
considered. Without one – **"All people, whatever their job functions"**
– Rentalars shows every active person, also those without a
job function, such as the office. Every person is

- 🟢 **free**,
- 🟡 **planned** – with the project they are in – or
- 🔴 **absent** – an absence, or they have entered red for this time ("Not
  available (own statement)"), or one of their linked calendars is busy
  ("Busy in the own calendar").

The free people come first, and among them first those who have entered
themselves as available in green ("has said they are available"). Yellow
entries – "with limits", with the person's note – are shown alongside;
they do not change the state, but the person moves to the back among the
free ones.

### Availability calendar

Every person keeps a calendar of their own in which they show when they
can work: **green** available, **yellow** with limits (with a note such as
"only until 18:00") or **red** not available. The person maintains it
themselves under **"My area" → "Availability"**; personnel planning sees
it in the person's **"Availability"** tab and, with write access, can
change it there for them – series too.

This is how you enter something:

1. In the month calendar, tap the **first** and the **last day** – or type
   the days into the fields "From" and "Until". For a single day, leave
   "Until" empty.
2. If you like, tick **"Only at certain times"** and enter "from" and
   "until" – then the colour applies on each of the days at these times,
   otherwise all day. And, if you like, a **note**.
3. Choose the colour: **"Available"**, **"With limits"** or **"Not
   available"**. **"Remove entry"** deletes what was entered for these
   days.

The calendar paints like a brush: a new colour replaces whatever was
entered for that time. The same colour with the same note directly next
to it appears as one period – first Monday, then Tuesday in green gives
"Monday to Tuesday". Below the calendar, the periods of the month are
listed with their origin – "entered", "series" or "busy in the linked
calendar" –, your own with "remove". A dot on a day means: planned. "‹"
and "›" page through the months.

**Month or week.** Above the calendar you choose **"Month"** or
**"Week"**; Rentalars remembers the choice. The week shows seven columns
with hours like the week calendar of the planning (section 15,
"Calendar"):

- the availability as a colour over its hours – green, yellow, red,
  hatched the busy times from the linked calendars;
- the **deployments** as blocks to the right of it; if a deployment falls
  in a red time, it has been filled red ("deployment although
  not available");
- at the top the days in the colour they have in the month. To enter
  something, you tap the head of the first and of the last day, then the
  colour – or enter "From", "Until" and times as usual.

**Marking a time range in the week**. In the week you mark a
time range directly in the columns: drag with the mouse from start to end,
in steps of 15 minutes – across several days as well; then the same hours
apply on each of these days. On the phone you tap the start first and then
the end (in steps of 30 minutes). Rentalars enters the days and times into
the form below, and a line above the colour buttons says in words what is
marked. Then you choose "Available", "With limits" or "Not available" and
can add a note. With the keyboard you fill in the same fields of the form.
For a night across midnight you enter the times in the form (end before
start) instead of dragging.

"‹" and "›" page through the weeks, "this week" jumps back. The week opens
at 06:00, with today's column in view. On the phone you slide the week
sideways and up and down. Below the week, its periods are listed as below
the month ("Entries in this week"). Personnel planning has the same choice
in the "Availability" tab of a person; projects it may not open appear
there only as "Job function · planned".

**Repeating like a recurring appointment.** Under **"Repeat …"** the
chosen days become the first appointment of a series:

- **daily**, **weekly** or **monthly**, and with it "every" 1, 2, 3 …
  days, weeks or months – "every 2 weeks" means every other week;
- weekly **on these weekdays**, for example Tue and Thu; with nothing
  chosen, on the weekday of the first day;
- monthly on the same day of the month; months without that day (the
  31st) are skipped;
- ends **on** a date **or after** a number of appointments, at most one
  year after the first day.

Then choose the colour. Every appointment paints like any other entry: it
replaces whatever was entered for its time, and whatever you enter later
replaces it. Below the calendar the **series** are listed with their rule
– "weekly on Tue, Thu, 18:00–23:00, from 03/11/2026, until 31/12/2026":

- **"Change"** opens the series: change colour, note, times, repetition
  and end, and state **from** which day this applies (otherwise from
  today). What lies before stays; from then on the appointments are set
  anew.
- **"Remove from this day"** ends the series on the day before;
  **"Remove all"** takes out all its appointments, past ones too.
- A single appointment can be overwritten or removed like any entry; it
  then no longer belongs to the series.

**One availability at any point in time.** Your own entries never
overlap. Busy appointments from the linked calendars (below) are a layer
of their own, which Rentalars takes over afresh every time it reads them –
that is why they do not overwrite your entries, and your entries do not
overwrite them. Where both meet, the **more recent statement** applies:
your entry with the moment you made it, the appointment with its change
date in the calendar. So if you enter "available" after a doctor's
appointment, green applies; if the appointment in your calendar is moved
afterwards, it applies again. If your calendar gives no change date, the
stricter statement applies – red. Appointments that overlap or adjoin
appear as one block.

**What planning gets out of it.** The colours appear under "Who is free?"
(above) and in the personnel plan (section 15), in each case as they apply
under these rules. Anyone who plans someone in a red period gets a warning
on the crew line ("Not available by own statement: …"), with yellow a
quieter hint ("Available with limits only: …"). Nothing is prevented.

### Linking calendars

If you keep your appointments in Google, Outlook, iCloud or Nextcloud
anyway, you don't have to copy them: under "My area" → "Availability" →
"Calendars" → **"Busy times from your calendars"** you enter the private
**ICS link** of a calendar, if you like with a **name** such as "Band",
and tap **"Link calendar"**. If you keep several calendars – your private
one, the band's, that of your other employer –, you link each one ("Link
another calendar (ICS link)"); up to ten. "Where do I find the link?"
explains where to find it in Google, Outlook/Microsoft 365, iCloud and
Nextcloud; a `webcal://` link works too.

- Rentalars reads **every calendar every 30 minutes** – the past month and
  the coming six months –, "Read now" reads all of them straight away.
- Every **busy** appointment counts as **"not available"**. The
  appointments of all calendars form **one** layer "busy in the linked
  calendar" and appear in the availability calendar as red time:
  overlapping and adjoining appointments appear as one block, even from
  different calendars. Where you have entered something yourself for the
  same time, the more recent applies (above). Appointments marked as free
  and cancelled ones don't count; recurring ones are expanded.
- **Rentalars never takes over the titles and contents of the
  appointments.** Planning learns *that* you are busy, not *why*. It
  doesn't see the links themselves either, only the name you gave and the
  server.
- Every calendar shows its state: "linked, last read …" or "Problem" with
  the reason. If one is stuck for a longer time, you are told once, with
  its name. Its times last read stay in place meanwhile; Rentalars keeps
  reading the other calendars as usual.

"remove" on a calendar cancels its link; only the times read from it
disappear. Personnel planning can link calendars for the person in their
"Availability" tab, read them now or remove them – it doesn't see the
links even then.

**Calendars in your own network.** Rentalars connects to
linked calendars and to your CalDAV calendar only if the address does not
lead into the internal network – that is, not to this computer, not into
private networks (such as 192.168.x.x or 10.x.x.x) and not to the server
itself. A NAS or a Nextcloud in your own network still works if the
operator allows it in the configuration file. Otherwise you see "The
address leads into an internal network. …" – with an IP address or
`localhost` as early as when you enter it, with a name when reading or
writing (section 16, "Self-check").

### Your own deployments in your own calendar

The other way round, you get your deployments onto your phone: under "My
personnel data" → "Calendars" → **"Your deployments in your calendar"**.
Every entry gives job function, project, place, meeting point, times and
the note for the crew – no customer, no prices; only what you see in the
overview of the project anyway. Three ways:

- **"Download as .ics file"** – a snapshot for importing.
- **Subscribing:** "Create subscription link" provides a secret link
  ("Copy") that you add in your calendar program as a subscribed calendar
  ("From URL", "Subscribe to calendar"). It then keeps itself up to date.
  The link works without login – keep it to yourself. "New link" makes the
  old one invalid at once, "Switch the link off" switches it off. For
  this, your calendar program must reach Rentalars over the internet;
  Google Calendar reads such a link too.
- **"Write into a CalDAV calendar"** – for the case that Rentalars runs
  only in the company network: Rentalars then writes your deployments
  itself into a calendar on the internet, for example at Nextcloud,
  iCloud, mailbox.org or Posteo. Address of the calendar or just of the
  server, username and password (often an app password), "Save and
  write". If you give only the server, Rentalars creates the calendar
  "Rentalars" there. After every change to a deployment, Rentalars writes
  again within minutes, and cancelled deployments disappear; "Compare now"
  does it straight away, "Disconnect" stops the writing. Best use a
  calendar of its own for this: Rentalars overwrites changes you make
  there to the entries. Google Calendar cannot be written this way.

What you have to enter for Nextcloud, iCloud, mailbox.org and Posteo is
explained right on the page under "Which address do I enter?".
Subscription link and CalDAV remain your business – personnel planning
doesn't see them. The calendar states its refresh interval
(30 minutes) in the form calendar programs read. You subscribe to the
bookings of products, models and items the same way, with their calendar
link (section 4, "Calendar link").

Rentalars sends the login data of your CalDAV calendar only
to exactly the server you entered them for – even if it redirects. If the
server refers to another server, enter the address of the calendar on that
server. The only exception is iCloud (`caldav.icloud.com` passes on to
`pNN-caldav.icloud.com`). A calendar in your own network needs the
operator's approval (above, "Linking calendars").

### Planning personnel in a project

On the planning page of a project, below the groups, there is the
**"Personnel"** block. Personnel belongs to the whole project, not to a
group, and has a subtotal of its own.

**Planning:** below the block, choose the job function, choose the person,
enter From and Until, "Plan". The crew line shows the article number of the
service product of its job function – a click opens it – and takes over
from it the price, the tax rate and the limit in hours per day (below,
"What personnel costs and earns"). New crew lines billed by hours are
billed **by effort**. A service cannot be planned as a material line
(section 7, "Adding a line").

- **Nobody chosen yet?** Leave "Person" at "– still open –" and enter under
  "Places" how many are needed: "2 × stagehand, Saturday 08:00–14:00" are two
  open places. At the top of the block you see how many places are open.
  They are filled later via the pencil.
- **Planned firmly (without request)**: if you tick it, the
  person is planned firmly straight away, without a deployment request –
  they get a message instead (below, "Planning firmly"). This works only
  with a person, not with open places.
- **Who is offered:** the "Person" selection lists only people with a job
  function, each with their job functions in brackets ("Becker, Anna
  (Stagehand, Sound engineer)"). If you have chosen a job function, only
  those who have it remain. Anyone with the special right "Plan people in
  job functions they are not assigned to" sees the others after them,
  marked, and can choose them anyway – a hint then appears on the row. If
  someone is missing altogether, they have no job function yet (above,
  "Job functions").
- **Phase:** if the project has phases, you choose the phase when planning
  – From and Until take over its period. The row then shows "Phase: Setup"
  below the period, and in the schedule the person is listed under their
  phase (section 7, "Schedule"). Without a phase, the line belongs to none;
  that works just as well.
- **New phase …:** if the phase does not exist yet, choose **"New phase …"**
  at the end of the list – in the form below the personnel and in the
  dialog of the crew line. A dialog asks for phase, label, from, until,
  venue and place, prefilled with the period you have already entered,
  otherwise following on from the latest phase – over several
  days at first one hour on the first day (section 7, "Schedule").
  **"Save phase"** creates it in the
  schedule and selects it straight away: job function, person, places and
  note stay, From and Until take over the period of the phase. "Cancel" or
  Esc closes the dialog, and the previous phase is selected again. With
  the keyboard: use the arrow keys to get to "New phase …", then Enter or
  Space. The entry is there if you may edit the project and it is not
  closed – anyone who only plans personnel does not create phases – and
  only with JavaScript switched on. If the project has no phase at all
  yet, the selection is still there – with "– no phase –" and "New phase
  …".
- **Planned hours** are suggested by Rentalars from the period: always the
  whole duration, end minus start. Saturday 08:00 to 14:00 is 6 hours,
  Monday 08:00 to Tuesday 20:00 is 36 hours – the period counts as worked
  through. If nobody works through, enter the actual hours via the pencil –
  for example 24 for two days of 12 hours each. Over the change to summer
  time a night is one hour shorter, and that is how Rentalars counts it.
  Lines that
  still carried an old suggestion were recalculated by the update: Monday
  08:00 to Tuesday 20:00 from 24 to 36 hours, Friday 12:00 to Saturday
  12:00 from 8 to 24. With billing "by plan" this also changes the amount –
  check such lines in running projects. Typed-in hours, closed and
  cancelled projects and documents already made stayed as they were.

**The pencil** opens the dialog of a crew line:

- job function, person, **phase**, **from / until**, planned hours – the
  "Person" selection follows the chosen job function as above; if you
  choose another phase, From and Until take over its period;
- **Meeting point** and **Note** – the person sees both in the "Overview"
  tab of the project;
- with the price right: **Billing**, **Price**, with "per day" the
  **Days**, **Limit in hours per day** and **Price per hour from the
  limit**, **Discount in percent** (see below) and **"Surcharges for
  night, Sunday and holidays on the price"**; if the job function allows
  less discount, that is shown below ("The job function allows at most
  10 %.");
- with the right for personnel costs: **Hourly rate (internal)**,
  **Hourly rate from the limit (internal)** and **Day rate (internal)** –
  taken over from the person on assignment, changeable here for this
  deployment only; if empty, the guide value of the job function applies
  –, **Flat rate for the person** and **"Surcharges for night, Sunday and
  holidays on the costs"** (below, "Surcharges for night, Sunday and
  holidays");
- as soon as a motor vehicle is booked in the project:
  **"Vehicle"** – which vehicle of the logistics the person travels with –
  and **"Drives the vehicle"** (section 7, "Logistics");
- **"Planned firmly (without request)"** – if you untick it,
  the line is "not asked" again and can be asked. Anyone who has accepted
  counts as planned firmly anyway.

The dialog "Personnel for this phase" in the schedule has the same box
(section 7).

**Warnings.** Rentalars lets you know, but prevents nothing:

- the person is **planned elsewhere** at the same time (in this or another
  project),
- the period falls within an **absence**,
- the person has entered themselves as **not available** for this time,
  or one of their linked calendars is busy; with "with limits" there is a
  quieter hint (above, "Availability calendar"),
- the job function is **not one of the person's job functions**.

#### Several crew lines at once

For everyone who may plan personnel, every crew line has a
box at the front too, like the material lines (section 7, "Several lines
at once"). As soon as one is chosen, the bar "Chosen crew lines" appears
at the bottom with:

- **"Set values …"** – a dialog with meeting point (or "Remove the meeting
  point"), note (or "Remove the note"), phase (or "without phase"), From
  and Until, planned hours, as soon as a motor vehicle is booked in the
  project the vehicle, and with the price right the discount in percent.
  Only what you fill in is set; what stays empty or at "– leave as it is
  –" stays as it is on each line. If you choose a phase without From and
  Until, the lines take its period. Empty planned hours follow the new
  period where they followed the old one; typed-in hours stay. **"Set for
  the chosen lines"** saves.
- **"Plan firmly"** – all chosen people without a request (below,
  "Planning firmly").
- **"Ask"** – one deployment request per person.
- **"Delete"** – after you confirm.
- **"Clear choice"**.

Each line follows the rules that apply to it on its own: a person asked or
accepted is asked again for new times, a person planned firmly is only
told. Lines where something is not possible – an open place cannot be
asked or planned firmly, a person planned firmly cannot be asked – stay
unchanged, and Rentalars names them with the reason. Every person
concerned gets **one** message, even if several of their lines were
changed. The bar deliberately does not set the job function – it changes
price and rates. Without JavaScript everything works the same, just via a
page of its own.

#### Requests: acceptance or refusal

Being planned is not the same as being asked. Below the name of a planned
person there is **"ask"**. The person gets a **deployment request** – in
the application and, if they have an e-mail address, by e-mail – and
**accepts** or **declines**, if they like with a note ("only from
10:00"): on their start page or in the "Overview" tab of the project – or,
if your installation is set up that way, **by reply mail**, without logging
in at all (below, "Answering deployment requests by mail"). Project
management and whoever asked learn the answer. Rentalars files a reply
mail in the mailbox like any assigned mail – into the folder
"Rentalars" even if the mailbox only marks assigned mails as read (section
14, "Assigned mails in the mailbox"): the inbox keeps the mails somebody
has to read.

If you prefer to ask on the phone – for example because the person has
never logged in –, you still press "ask". The row is then set to "asked",
and you enter the answer yourself ("enter: accepted" or "declined").

**Accepting marks "available"**. If a person accepts for a
time in which their own availability calendar shows **"not available"** –
in the browser, by reply mail, in the app or through the interface, or you
enter their acceptance –, Rentalars marks exactly the time of the line as
**"available"**, with the note "Accepted: 2026-0042 Stadtfest – Sound
technician". Entries reaching into this time are shortened or split, also
occurrences of a series. The confirmation says so ("For …, “available” is
entered now."). If the calendar shows nothing "not available" there,
nothing changes. Linked calendars stay as they are; the new entry is an own
entry of the person and counts as the newer statement over a busy time
from them (above, "Availability calendar"). Planning firmly (below) marks
nothing – that is a decision of the office, not of the person –, and if
the deployment is removed later, the entry stays: it is the person's
calendar.

The row shows the state: **asked** (yellow), **accepted** (green),
**declined** (red), also **planned firmly** (green). A refusal
prevents nothing – the line stays until you
plan another person. If the person changes, the request starts from
scratch. In the personnel plan, requested deployments are paler and dashed
(section 15).

**Planning firmly**. Sometimes it was agreed long ago who is
coming – then you plan the person **without a request**: with the box
"Planned firmly (without request)" when planning or in the dialog, with
**"plan firmly"** on the row (for a line that is not asked, asked or
declined) or for several lines in the bar (above). It counts like an
acceptance: the deployment is listed under My deployments, in the
calendars and in the person's overview, and in the personnel plan as
planned. The person gets no request but the message "Planned firmly: …"
with meeting point and note. If the times change later, Rentalars does
**not** ask them again – they stay planned firmly and are told the new
times. You take it back in the dialog; the line is then "not asked".

**Messages about the deployment**. The planned person learns
by themselves – in Rentalars, by e-mail and in the app, as the
notification "Change of my deployment" (section 15, "Notifications"):

- that they have been **planned firmly**;
- that the **times, meeting point, note, phase, job function or vehicle**
  of their deployment have changed – each with the value before;
- that they have been **taken off** – the line deleted or given to
  someone else.

There is **one** message per person and action: if you change several
lines at once or move a phase or the rental period together with the
personnel, it names all the person's deployments concerned together. If
the person is asked again for new times (below), the request names the
other changes too. There is no message when you change your own
deployment, for declined lines, past deployments, cancelled projects and
people without an active account.

**Answers appear straight away.** If someone accepts or declines – in the
browser or by reply mail –, the open planning shows it by itself, at the
latest about 20 seconds later; with a reply mail, as soon as Rentalars has
fetched the mailbox. This also applies if you have saved something
yourself in the meantime. If you are typing at the moment, "There is
something new on this page." appears at the bottom (section 2).

**"ask again"** only appears once the **start or end** of the line has
changed since the request. The row then says, for example, "Times changed
since the acceptance – asked for: Wed 10/03 08:00 – Wed 10/03 18:00" (or
"… since the refusal", "… since the request"). For the same times,
Rentalars does not ask again; an accepted or declined line with unchanged
times shows only its state.

**New times, new request.** If you change the start or end of a crew line
that is **asked or accepted** – in the dialog, with "Move the crew of this
phase along" (section 7) or via the interface –, Rentalars asks the person
again by itself; after the dialog and after saving the phase it tells you
so ("Anna Becker was asked again for the new times."). The request is
called "Deployment request with new times: …" and states "New times: …
(before: …)"; the row is set to "asked" again until the answer comes.
Rentalars no longer takes over an answer to the older request mail. Not
asked again automatically are:

- **declined** lines – there "ask again" appears, and you decide;
- lines **planned firmly** – the person is told the new
  times (above, "Messages about the deployment");
- lines of a cancelled project and deactivated people;
- changes to hours, meeting point, note or job function – they do not
  trigger a request; the person gets a message for meeting
  point, note, job function, phase and vehicle.

This can be switched off under Settings → Company data and settings
→ **"Ask again when the times change"** (on by default; section 16). Then
the state stays as it was after a change of times, and the row offers "ask
again".

#### Answering deployment requests by mail

**For you as crew.** You get the request as a mail "Deployment request: …"
with project, job function, time, place and meeting point and the buttons
**"Accept"** and **"Decline"**. Tap one of them: your mail program opens a
ready-made mail. After **"Note:"** you can write something for the
planning, for example "won't be there until 9". Leave the subject as it is
– it contains the code in square brackets by which Rentalars recognises
your answer – and send the mail. As soon as Rentalars fetches the mailbox,
usually after a few minutes, you get the mail **"Your acceptance has
arrived"** (or "Your refusal …"). If the request has already been
answered, the deployment is over, the request has been withdrawn, the
project has been cancelled or closed, or there is a newer request, you
instead get a mail saying that nothing was taken over, and why. Rentalars
does not evaluate an ordinary reply with "Yes" or "No" – it ends up with
whoever reads the mailbox. Don't forward the request: whoever has the code
can answer for you. If the mail also says "Or answer in Rentalars", both
work. By mail only the first answer counts; if you want to change it
afterwards, let the planning know. If the times of a deployment you have
been asked for or have accepted change, you get a new mail "Deployment
request with new times: …" with the new and the previous times ("the
times of your deployment have changed. Do you take it at the new
times?"). Answer with the buttons of this latest mail – those of the older
one no longer count.

The table in the mail begins with the line **"Company:"**
and the name of your company, before "Project:" – so that someone who
works for several companies sees at once whose request it is. The name
comes from Settings → Company data. Every active person with an e-mail
address gets the mail with the buttons,
even those who never log in – provided answers by mail are switched on
(below). Anyone who has switched off the mails about deployment requests
under My account → Notifications gets none; the request then exists only
in Rentalars.

**For the planning**, an answer by mail looks like one from the browser:
the row is set to "accepted" or "declined", with the note, and project
management and whoever asked are notified. The history of the project
says "Answer of … came by reply mail".

**Only from the address the request was sent to.** The code in
the subject alone is not enough: an answer counts only if the mail comes from
exactly the address the request was sent to (upper and lower case do not
matter). If somebody forwards the request, the new recipient cannot accept
in the name of the original one: their answer changes nothing, it appears in
the mail log with the reason "not from the address the request was sent to",
and the person gets a mail at their own address saying that an answer came
from another address and nothing was changed. Whoever wants to answer from
another address answers in the browser or asks the planning to send the
request again. Rentalars stores the address with the request; if the address
of the person changes afterwards, the old one still applies to that request.

A sender address can be forged. If the mail server that receives the answer
writes a verdict (`Authentication-Results`) into the header of the mail and
says in it that the DMARC check failed, Rentalars does not take the answer
over either ("the check of the sender failed"; this includes a domain whose DMARC is only for
observation, `p=none` – whoever sends "on behalf of" another address answers in Rentalars instead). A mail with
two `From` lines is not taken over either, and the warning mail comes at most once an hour per request. Without such a verdict
Rentalars cannot check the sender any further; many mail providers write it
when the sender's domain has DMARC set up.

**For administrators: setting it up.** Under Settings → Company data
and settings there is the setting **"Answer to deployment requests"**
(whoever may change the settings may change it):

- **"by the link in the browser"** – the mail
  contains only a link to Rentalars.
- **"by reply mail"** – the mail contains only the buttons "Accept" and
  "Decline", no link.
- **"both"** (the default) – buttons and link.

Answers by mail need an **active mailbox of the correspondence with an
address** that Rentalars fetches: the mailbox for the system mails if it
is also correspondence, otherwise the outgoing mailbox of the
correspondence (section 14, "Setting up mailboxes"). Below the setting,
the page says where the answers go – or that there is no such mailbox yet;
then the requests contain only the link, even with "both" and "by reply
mail". Rentalars recognises answers in **every** mailbox it fetches,
whether or not that mailbox takes in mails without a project tag, and then
treats them like assigned mails: move, delete or leave them. In the mail
log they appear with the result "answer to a deployment request" and
"acceptance", "refusal" or the reason why nothing was taken over (section
14, "Mail log"). The sender address of a mail can be forged. Whoever enters the
name of the mail server in the check results under Settings → Mailboxes
(operations manual) lets only answers count that this server confirmed;
without the entry a reply mail is no proof of who wrote it.

**Does this work without being reachable from the internet?** Yes. The
link in the request leads into Rentalars and works only where Rentalars
can be reached – if it runs only in your own network or via VPN, it leads
nowhere from outside. The "Accept" and "Decline" buttons, by contrast,
open a ready-made mail to your mailbox with a code in the subject that
cannot be guessed. Rentalars fetches this answer itself from your mail
provider, like the other mails; the connection only goes from inside to
outside. Then set "by reply mail", so that nobody follows a link that
does not work.

#### Price offers of freelancers

A freelancer who is asked for a deployment does not have
to accept the stored rate: they can name **their own price**, and you
accept it, reject it or answer with a counter-offer. The feature is
**off by default** – as long as it is off, a request is answered with
"Accept" or "Decline" only, exactly as before.

**Switching it on.** Under Settings → **"Price offers of freelancers"**
(the page also opens from "Settings" on the Personnel tab "Price offers";
you need the right to change the settings):

- **"freelancers may offer their own price"** – the switch.
- **"temporary staff too"** – off: only people of the kind "freelancer"
  can make an offer; on: people of the kind "temporary staff" too.
  Permanent employees never can.
- **"lowest offer in percent of the stored rate"** and **"highest offer
  in percent of the stored rate"** – both optional. An offer outside
  them is refused. They compare the offer with the rate stored for the
  person: per hour or per day with the rate of the crew line (the person's
  own rate, otherwise the guide value of the job function), in total with
  the flat rate of the line or, without one, what the line costs now.
  Without a stored rate no limit can be checked. Your own counter-offers
  are not limited.
- **"proposals per request, at most"** – 4 by default, 1 to 10. Offers
  and counter-offers count together; after the last one the other side
  can only accept or reject.

**For the freelancer.** In the mail with the request there is one more
line, "Want to name your own price? You can make an offer in Rentalars:",
with a link – only if the person has an account with a password. In
Rentalars the offer starts from the start page (beside "Accept" and
"Decline": **"Make a price offer"**) or from the "Overview" tab of the
project (box **"Your price offer"**). The form asks for:

- **"Amount"** in euros without VAT, at most two decimal places;
- **"Per"** – "per hour" (or "per day" for a line billed per day) or
  "in total";
- **"Message"** – optional, up to 500 characters;
- **"Valid until"** – optional; until the end of that day the offer can be
  accepted.

An offer is possible while the deployment request waits for an answer and
the project is not cancelled or closed. While an offer waits, the
freelancer can take it back (**"Withdraw offer"**). If you answer with a
counter-offer, the box says "Counter-offer: …" and offers **"Accept
counter-offer"**, **"Reject"** and, while there are rounds left,
**"Counter again"**. Under "Exchange so far" they see every round. A
freelancer sees only their own offers, and the stored rate only if they
may see their own rates (they have the right "See hourly rates and
personnel costs" or the setting "people may see their own hourly rates"
is on).

**For you.** Whoever plans the crew of the project **and** has the right
"See hourly rates and personnel costs" sees the offer in the planning
below the request of the crew line: the badge "price offer", the amount
with "per hour", "per day" or "in total", "stored: …" with the percentage,
the date and the message. Beside it:

- **"accept offer"** – the deployment is **accepted** (the note says
  "Accepted after a price offer."), and the **cost rate of exactly this
  crew line** is set to the offer: "per hour" becomes the hourly rate of
  the line (a rate above the hour limit and a flat rate of costs are
  removed, the offered rate holds for every hour), "per day" the day rate
  (a flat rate is removed), "in total" the flat rate of costs. The row marks it with "price offer" below the costs,
  with "stored: …" for comparison. **The price for the customer does not
  change** – an offer is a matter of costs only.
- **"reject"** – the request stays open; the freelancer may offer again
  while there are rounds left.
- **"counter"** – opens a form with the same fields; the freelancer then
  answers. The badge says "counter-offer sent", and you can take it back
  with "withdraw counter-offer".

Under Personnel there is the tab **"Price offers"** (only while the
feature is on, and only with that right): the list "Waiting for an answer"
or "All", each with project, person, period, "Stored rate", "Offer" in
euros and percent of the stored rate, the status and the buttons
"Accept", "Reject" and "Counter" or "Open planning". After switching the
feature off, earlier offers stay visible there. You are told by the
notification **"Price offer of a freelancer"** – the project manager, whoever
asked and the personnel planners, as far as they see personnel costs and
the project –, the freelancer by **"Answer to my price offer"** (My
account → Notifications; section 15). Both go by e-mail by default and
are off in the companion app until somebody switches them on there.

An accepted offer **stops applying** when you change the cost rate of
the line by hand or give the line to another person or job function – the
rates stay as they are then, only the marker "price offer" goes – and, for
an offer "in total", when the person is asked again for new times – then
the rates from before come back. If a later offer is accepted for the same
line, the earlier one is taken back first and the rates from before come
back before the new offer is applied. An offer that was not answered by its "Valid until"
day is shown as "expired". A new request starts a new negotiation.

*Limits:* amounts are in euros only and have at most two decimal places;
nobody may take more than 30 offer actions per hour. If you have no
right to see personnel costs you see nothing of the offers in the planning
– a freelancer's offer then waits for someone who has it. A price agreed
on the phone cannot be entered in the planning by a button yet; the
interface can (section 16, "API tokens – Rentalars for other programs").
A freelancer without a login cannot make an offer themselves.

#### What personnel costs and earns

For each row, the block shows hours or days, price, amount – and, with the
right for it, the costs.

| Billing | Amount for the customer | Example (€45.00 per hour, €400.00 per day) |
|---|---|---|
| **by plan** | planned hours × price | 8 h → €360.00 |
| **flat rate** | the price, regardless of the hours | €300.00 |
| **by effort** | approved hours × price; until approval, the planned hours, marked as an **estimate** | 9.5 h → €427.50 |
| **per day** | days × price per day | 2 days → €800.00 |

The billing of a new crew line follows its service product: a product
billed by hours – the default – or by effort makes it **"by effort"**, a
flat-rate one "flat rate", one with daily rental "per day". So "by effort" is the normal case: the approved hours are
charged. Existing lines keep their billing. On the line you can change the billing, and the price too.

The **costs** are planned hours × the person's hourly rate. If the person
has no hourly rate of their own in this job function, Rentalars uses the
guide value of the job function and writes "guide value" below the costs
– likewise for an open place. If a **flat rate** has been agreed with the
person, it applies – regardless of the hours and regardless of how the
customer is charged.

**Per day.** The days are the calendar days the period touches: Monday
08:00 to Tuesday 20:00 is 2 days, Saturday 22:00 to Sunday 04:00 as well;
an end exactly at midnight does not count the new day. In the dialog you
can overwrite the days. The costs are then days × the person's **day
rate** – taken over on assignment like the hourly rate, otherwise the
guide value per day of the job function. If there is no day rate at all,
Rentalars calculates hours × hourly rate as before. On offer, order
confirmation and invoice the number of days appears with the unit "day".

> **Example.** Anna, sound, 8 hours: price 8 × €45.00 = €360.00, costs
> 8 × €35.00 = €280.00. If you agree a flat €300.00 with Anna, the costs
> are €300.00 – the price stays €360.00. The same Anna per day, Monday
> 08:00 to Tuesday 20:00: price 2 × €400.00 = €800.00, costs 2 × €280.00
> = €560.00.

**More expensive above a daily limit.** Long days cost more: on the
service product you enter a **"Limit in hours per day"** and the **"Price
per hour from the limit (net)"**, e.g. 10 and €55.00 – then from the
11th hour of a day, every hour costs €55.00. For the costs, you enter the
**"Hourly rate from the limit"** on the person per job function (if it is
missing, their hourly rate applies) and on the job function the **"Guide
value per hour from the limit"** for open places and people without a rate
of their own. Counting is per calendar day and per line:

- **by plan** the planned hours, as they fall on the days – Monday 08:00
  to Tuesday 20:00 is 16 and 20 hours; hours entered by hand are spread
  evenly by Rentalars over the days of the period;
- **by effort** the approved times, each on the day it starts;
- with **flat rate** and **per day** there is no limit.

A new crew line takes over the limit and the price from the limit from the
product, like the price itself; in the dialog of the line they can be
changed (with the price right), the hourly rate from the limit with the
right for personnel costs. The planning shows below the price "from 10 h a
day: €55.00" and below the amount "of which 2 h beyond the limit"; price
overview, offer, order confirmation and invoice write "of which 2 h beyond
10 h a day at €55.00".

> **Example.** Sound engineer at €45.00 per hour, from 10 hours a day
> €55.00; Anna works on Monday from 08:00 to 20:00, by plan: price
> 10 × €45.00 + 2 × €55.00 = €560.00. With her hourly rate of €35.00
> and €42.00 from the limit, she costs 10 × €35.00 + 2 × €42.00 =
> €434.00.

The price overview lists personnel as a block of its own, broken down by
phase and job function if you like (section 8, "The price overview").
Hourly and day rates never appear there.

#### Surcharges for night, Sunday and holidays

Hours at night, on Sundays and on holidays can cost
more if you wish – in the **price for the customer**, in the **personnel
costs** or in both. Which rules apply and whether new crew lines get the
surcharges is set under Settings → Surcharges (section 16). The surcharges are a list of rules that works in any country; preset
are the tax-free rates under § 3b EStG (German income tax act), and both
switches are off to begin with.

- **Which lines:** only crew lines **by plan** or **by effort** – never a
  flat rate or a line per day; no surcharges on the costs if a flat rate
  has been agreed with the person. Material, incidental costs, surcharges
  and every other line never get them; that is why only services have the
  switch to exclude them.
- **On the line:** every crew line has two switches of its own in the
  dialog: "Surcharges for night, Sunday and holidays on the price" (with
  the price right) and "… on the costs" (with the right for personnel
  costs). A new line gets them from the settings, unless its service
  product excludes the surcharges (section 5, "Creating a product"). Lines
  that were already planned are not changed by switching the settings –
  nor are older ones; there you switch them on in the dialog
  if needed.
- **Which hours:** by plan the planned period, by effort every approved
  time – with the break deducted proportionally. If you have entered the
  planned hours by hand, Rentalars spreads them over the days as with the
  daily limit, and proportionally within the day. The hours that really
  pass are counted: the night of the change to summer time is one hour
  shorter.
- **How they combine:** of the rules on weekdays, holidays and days of the
  year only the highest rate counts, of the rules at a time of day
  likewise; the two are added. With the rules under § 3b EStG this means:
  the night surcharge is added to a Sunday or holiday surcharge; of
  Sunday, holiday and Christmas/1 May only the highest counts. A holiday
  falling on a Sunday, at 22:00: 25 % + 125 %. If work began before
  midnight, from 00:00 to 04:00 the rule "Night 0–4" applies
  instead of the night, and a Sunday or holiday lasts until 04:00 on
  the next day (adjustable). Price and costs each choose their rule
  separately.
- **With the daily limit** (above), the surcharge is a percentage of the
  price or rate that applies to that hour; the hours above the limit are
  the last ones of the day.
- The **discount** of the line also applies to the surcharges.

The planning shows **"incl. surcharges …"** below amount and costs, and
below that each rule with its label – rules with the same label and the
same rate as one row, for example "Christmas and 1 May" –; price overview,
offer, order confirmation and invoice list them in the same way.

> **Example.** Sound engineer at €45.00 per hour, Saturday 18:00 to
> Sunday 02:00, by plan, surcharges on the price switched on: amount
> €486.00 – 8 × €45.00 = €360.00 and "incl. surcharges €126.00: Night
> 25 % on 4 h €45.00, Night 0–4 40 % on 2 h €36.00, Sunday 50 %
> on 2 h €45.00".

If someone changes a rule, a rate, the holidays or the federal state under
Settings → Surcharges, every line with surcharges is recalculated
straight away – in closed projects too; documents already made stay as
they are.

#### Planned and worked

As soon as times have been approved (section 13), every crew line shows
the **hours worked** next to the planned ones. Rentalars assigns an
approved time to the line with the same person and job function.

If someone has worked without being scheduled for this job function,
**"Approved times without crew line"** appears below the block. With "Take
over" you assign them to an existing line or make a new one from them – so
that no work done gets lost.

### The overview – what the crew sees

The **Overview** tab of a project is
what planned people see of a project:

- **When and where:** period, venue, contact on site;
- **Schedule:** the phases with time and place;
- **the venue** with address, contact person, access and power, with
  "Route in Google Maps" from where you are right now (section 6, "Route
  and map");
- **My deployment:** job function, time, meeting point, note,
  the vehicle you travel with ("Vehicle: … – you drive"), your own hourly
  and day rate ("My hourly rate here", "My day rate here"), if your
  company shows it to you – and, if you have been asked, the buttons
  "Accept" and "Decline"; if your company has switched on
  price offers and you are a freelancer, also "Make a price offer" (below,
  "Price offers of freelancers");
- **Trips:** the trips of the project with the vehicles on them, their
  route in Google Maps and the map of the places – for everyone who drives
  (section 7, "The trips of a project");
- **Files for the crew:** stage plan, rider, running order, hall plan,
  show files with console, version and "current show" – not the contract;
- **Crew:** who else is involved, in which job function, when and with
  which vehicle;
- **my times** in this project and the button "Record time";
- **my expenses** in this project and the button "Record expenses"
  (section 13, "Expenses and travel costs").

Planned people have the **packing list** for reference and the **chat** of the
project (section 7, "Chat in the project") as tabs of their own,
also the **correspondence** – with the open messages, for reading, once
they have accepted or are planned firmly (section 14, "Messages with a
lock").

They do **not** see: prices, calculation, the customer, the planning, the
messages of the correspondence with a lock, the hourly and day rates of
others.

**With the role Crew**, overview (with the phases), packing list and chat
are the only tabs of its projects, plus the
correspondence with the open messages – even if someone has
entered the person under "Access" with the level "read" or "edit".
Planning, schedule, access, history, documents, subprojects, the open
items and the shortages stay closed to it, also via the interface; a link
to the planning leads to the overview. This is governed by the role's
project access "assigned projects only, overview without planning"
(below, "Who sees which project").

**Contact data of colleagues.** The name is always visible. A colleague
sees phone and e-mail only if the person has released them themselves.
Project management and personnel planning always see them.

Anyone who may read the project uses the same tab as a crew overview.

**Printing.** At the top right of the tab is **"Print / PDF"**: it opens
the **deployment overview** as a PDF (it keeps that name) – with
letterhead and footer like the documents and with everything you see in
the tab: when and where, schedule, venue, your deployment, the crew, your
times, with "As of" and the time at the top. It never contains prices,
hourly and day rates or the customer. It gets no number and is not filed;
the file name is `Einsatzuebersicht-2026-0042.pdf`. The page itself can
also be printed straight from the browser; tabs and buttons are left out.

The deployment overview can also be **attached to a mail** (section 14,
"Writing and answering") – then as seen by any colleague. Filed permanently
with a number, there is the **crew disposition** (section 11).

### My area

*For everyone – every account is a person: the **"My area"** entry in the
sidebar. No right for personnel is needed for it.*

My area opens with "My deployments". The tabs:

- **My deployments:** all deployments you are planned in, as a table like
  any list (section 2, "Lists") – Project, As, From, Until, Phase, Place,
  Meeting point, Planned hours, State and Request, with column choice,
  sorting, "Group by" and CSV; the column "Vehicle" (under
  "Columns") names the vehicle you travel with. The filters first show the coming
  deployments (a running one stays listed for twelve more hours after its
  end); choose "past" or "all", a period with From and Until, the state
  (firm, option, inquiry), the request (asked, accepted, declined, not
  asked) or a project. Cancelled projects are left out. A click on the
  project opens its overview. On the start page, "All my deployments" leads
  here.
- **Availability:** the availability calendar – green, yellow, red, as a
  series too, as a month or week, in the week with marked time ranges
  (above, "Availability calendar") – and next to it the **Calendars**:
  take over busy times from your own calendars and bring your deployments
  into your calendar (above, "Linking calendars" and "Your own deployments
  in your own calendar").
- **My times:** your times week by week (section 13).
- **My expenses:** your expenses and travel costs month by month, with
  "Record expenses" (section 13, "Expenses and travel costs").
- **Report** – only for those who see only their own times: your own
  hours with the timesheet (section 13).
- **Service cases**: the service cases you are involved in
  or responsible for (section 7, "Service cases").
- **Personnel data** – also via "My account" → "My personnel data":
  - **Contact data and colleagues:** maintain phone and e-mail and tick
    whether colleagues on the same deployment may see them. The default
    is: no.
  - **My job functions** – with your hourly rate and day rate, if your
    company shows them to you; otherwise just the job functions.
  - **My deployments** – the coming ones.
  - **When I am not available:** enter an absence with kind and period.
    Planning sees it straight away in the availability.
  - **My qualifications** – with expiry date and certificate, for
    reference; personnel planning enters and changes them.

### Who sees which project

Rights first apply to a whole module (section 16). For projects there is a
second question: **for all – or only for assigned ones?** The role decides.

- A role with **"all projects"** (project management, warehouse, planning)
  applies in every project.
- A role with **"assigned projects only"** applies only
  where the user is assigned. All other projects do not exist for them –
  not in the list, not in the search, not via an address.
- A role with **"assigned projects only, overview without planning"**
  (Crew, Freelancer too) likewise applies only in
  assigned projects, but
  opens at most overview, packing list and chat there – plus
  the open messages of the correspondence –, whatever level a membership
  names (above, "The overview – what the crew sees").

You get assigned in two ways:

1. **Automatically**, when your own person is planned in the project. That
   gives the level **deployment view**: the tabs "Overview", "Chat" and
   "Packing list",, after accepting or when planned firmly,
   also "Correspondence" with the open messages.
   Whoever is **responsible** for a **service case** or
   **takes part** in it works on it – whatever their role says
   (section 7, "Working on the case").
2. **Explicitly**, via the **Access** tab of the project: choose the user,
   choose the level, "Add member".

| Level | Shows |
|---|---|
| **deployment view** | time, place, job function, colleagues, trips, packing list, chat, own times and expenses; the open messages of the correspondence, if one has accepted or is planned firmly |
| **read** | in addition the planning, without being able to change anything |
| **edit** | planning, groups, lines, status |
| **no access** | nothing – can only be chosen in a subproject (below) |

Two rules that save you surprises:

- A membership **never gives more than the role allows**. Anyone whose
  role lets them only read projects also only reads as a member with the
  level "edit".
- **Prices, costs and correspondence** do not depend on any of these
  levels. They only come from the special rights of the role. The one
  exception: the crew planned in reads the open messages of
  the correspondence once it has accepted (or is planned firmly) (section
  14, "Messages with a lock").

**Who has access**. The **Access** tab of a project or
service case shows in the table **"Who has access"** everybody assigned to
it – not only the members –, each row with **User**, **Access** and
**Why**:

- members ("member: edit") – only these rows can be changed here
  ("remove", "Add member");
- members of the whole project in a subproject ("member of the whole
  project 2026-0042: read" – "From the whole project – a membership here
  replaces it.");
- the crew planned with an account ("planned as Sound technician" – "From
  the planning – changes with the crew line.");
- in a service case, whoever is responsible or takes part ("responsible
  for the service case", "takes part in the service case" – "From the
  service case – changes there.").

"Access" is what the person may **really** do in this project, after their
roles – e.g. "deployment view" for a membership "edit" with the role Crew.
If their role for all projects gives more than the assignment, the reason
says "role for all projects". An account that cannot log in – without a
password, deactivated or past its "valid until" – shows "no access –
cannot log in", like the data access columns (section 12, "People").
Whoever gets in only through a role for all
projects without being assigned is not listed, as before – such roles
hold everywhere anyway.

**Subprojects** (section 7): members of the whole project have the same
access in all subprojects; the Access tab of a subproject lists them with the reason "member of the whole project 2026-0042: …". Under "Access" of a subproject you give
a member different access there – more, less or **"no access"**. A
membership only in a subproject opens only that one, not the whole project
and not the other parts. Anyone planned in a subproject sees its overview
and packing list in any case.

---

## 13. Time tracking

*For everyone with access to time tracking. Times are recorded for your
own person – every account is at the same time a person in personnel
(section 12). Your own times are under "My area" → "My times", your own
expenses under "My expenses", approval, report and expenses under
"Personnel"; anyone who sees only their own times finds the report under
"My area" as well.*

### Recording time – in a few seconds

The **"Record time"** button is on every page: below the sidebar, on the
phone as a clock at the top right. It opens a small dialog; the page
behind it stays where it was.

1. **Project** – prefilled with the project you are currently planned in.
   Your other deployments and the internal projects follow. A subproject
   is listed with its whole project: "2026-0042-1 Bühne Marktplatz
   (Stadtfest)". All open service cases are also listed under
   **"Service cases"** (below, "Times on service cases").
2. **Job function** – prefilled with the job function from your
   deployment. "Job function" is never empty: first come your
   own job functions and those you are planned in for the project, then
   the other job functions the project's crew is planned in (open places
   and subprojects too). If you have no job function of your own and
   nobody is planned in the project, you choose from all active job
   functions – as on a service case. Your deployments in the
   project are listed at the top under **"Planned for you"** with job
   function, phase and times, for example "Lighting – Setup, Wed 10/03
   08:00–12:00" – so it is clear which deployment is meant if you are
   planned several times in a project. If you choose one of them, the time
   counts towards exactly this crew line; if you only choose the job
   function, Rentalars finds the matching line by the time of day as
   before.
3. **Day**, **Begin**, **End** – if the end is before the start, the
   following day is meant: 22:00 to 02:15 is 4.25 hours.
4. **Break** in minutes and a **note**, if needed.
5. **"Save time".**

The dialog confirms with hours, job function and project – and with a hint
if the time stands out (below, "Hints at unusual times"). "Another
time" brings back the form, "Record expenses" opens the dialog for
expenses for this project straight away (below), "Done" closes it.

**Stopwatch.** Instead of typing in start and end: "Start stopwatch" – and
later, via the same button, "Stop". The clock runs on the server; you can
close the browser and put the phone away.

**Several job functions in one period**. If you have worked
from start to end in more than one job function – lighting in the
morning, stagehand in the afternoon –, open **"Several job functions in
this period"** when recording. Under "Further job function 1", "Further
job function 2" … enter each further job function (or each further
deployment) with its hours; the job function at the top gets the
remaining hours. Together the parts add up to the hours of the period.

- Each part counts with its job function and its rate towards its crew
  line – in the totals, the report, the exports, the costs and for the
  surcharges, which are distributed according to the hours of the parts.
- The period counts **once**: for the hints (the break counts once), for
  the check for overlaps and when handing in, approving, sending back and
  deleting – that always applies to the whole period.
- If you change start, end or break, they change for all parts, and the
  hours of the parts grow or shrink in the same proportion.
- A running stopwatch cannot be split – split the period after you have
  stopped it.
- In the lists, every part shows which one it is, for example "Part 1 of 2
  of a period of 8 h"; when approving, a split period has a tick mark.

**Times on service cases**. You can record times on any open
service case – open or in progress –, even without being planned, and with
any job function. Cases you are involved in (section 7, "Service cases")
come first, prefilled with the job function you are involved with; after
them all other open cases.

**What isn't possible:**

- two entries of the same person at the same time. The second is refused
  with a reference to the first;
- **times in the future.** What is recorded is work that has been done.
  The message gives the time of the server – if the clock of your phone is
  wrong, you notice it this way. The stopwatch is not affected: it starts
  now;
- more than 24 hours in one entry.

**Times without a customer project** – warehouse, workshop, office – you
book on an internal project (section 7).

**Project not known yet?** In the Project field choose **"assign later"**.
The job functions from your master data are then offered – if you have
none, all active job functions. The time is
saved, but can only be **approved** once it belongs to a project: assign
it under "My times" as soon as you know it (pencil) – or whoever approves
does it when approving.

The **hourly rate** is determined when recording and stored on the entry:
your own rate in this job function, otherwise that of the crew line,
otherwise the guide value of the job function. Later changes to your rate
do not change it.

**No network at the site?** With the **Companion app for Android**
(Rentalars Companion) the stopwatch runs on the phone, and you can enter
times even without a network – on open service cases too; as soon as the
phone has a network again, they arrive here – each exactly once and with
the same rules as in the browser (section 2, "The Rentalars app for
Android"). You create the access for the app under My account → API
tokens.

### Hints at unusual times

Rentalars points out times that stand out under the German Working Hours
Act (Arbeitszeitgesetz):

| Hint | by default |
|---|---|
| **Long working day** | more than 10 hours of work on one working day, not counting breaks |
| **Short break** | with more than 6 hours of work less than 30 minutes of break, with more than 9 hours less than 45 minutes |
| **Short rest** | less than 11 hours between the end of one working day and the start of the next |

The calculation is per person and **working day**, across all projects –
including those you may not see; the hint then gives only hours, never the
project. The recorded break and gaps of 15 minutes or more between the
entries of the day count as a break. A new working day begins after a gap
of at least the rest period (11 hours) – or of at least 3 hours if the
next entry begins on a later date. Rejected entries and a running
stopwatch don't count.
"Long working day" and "Short break" appear on every entry of the day,
"Short rest" on the first entry of the new day, for example "Short rest:
9.5 hours since the end at 23:30 on 14/10/2026 (less than 11)."

The hints appear right after saving ("Please check:" – "The time is saved.
If it is right, nothing needs to be done."), under "My times", when
approving and in the report, also in the CSV (last column "Hints") and in
the timesheet. They **hold nothing up**: the time is saved and can be
approved like any other. An administrator sets the limits under
Settings → Company data and settings; 0 switches a hint off (section
16). **"Show hints at working times"** there switches all
hints on or off for everyone at once – when recording, under "My times",
when approving, in the report and in the Companion app; the limits stay
saved. When it is off, the report lacks the tick box "Only entries with
hints", and the "Hints" column in the CSV stays empty. The same hints
apply to permanent employees, temporary staff and freelancers. This does
not turn time tracking into a record of working time in the legal sense.

### Handing in and approving

Every entry has a status:

| Status | Meaning |
|---|---|
| **recorded** | written down, still with you |
| **submitted** | handed in for approval; you can still correct it |
| **approved** | checked and **locked**; counts in the project and in the report |
| **rejected** | sent back, with a reason; correct it and hand it in again |

The tick box **"Hand in for approval right away"** in the dialog is ticked
– so a saved entry is handed in at once. If you untick it, the entry stays
with you until you hand it in under "My times".

**Approving** (Personnel → "Approve" tab, with the special right "Approve
times and record them for others" – project management and personnel
planning have it): the waiting times are listed by project, all ticked,
conspicuous ones with their hint (above); below them, for each project,
the submitted **expenses** are listed and are decided with the same buttons
(below, "Expenses and travel costs").
Times **without a project** are listed in a block of their own at the top;
every row there has a project selection and "Assign". Only after that can
they be approved – the person sees the assignment in their times.
"Approve the ticked" approves them all together; you untick individual
ones beforehand. The filters let you narrow down by project, person and
period. "Send back the ticked" requires a reason – the person should know
what to correct.

**Correct and approve**. If only a detail is wrong – the
break is missing, the end was mistyped –, you need not send the time back:
**"Correct"** at the end of the row opens the dialog "Correct and approve"
with project, job function, day, start, end, break and note, and above
them what the person handed in. **"Save and approve"** saves your
correction and approves the time at once. The same rules apply as when
recording – nothing in the future, no overlap, a job function the person
may book on the project –, and the new project too must be one you may
approve for. For a part of a divided period, times, break, project and
note hold for the whole period, the job function for this part; the whole
period is approved. What was entered before stays in the change log, and
the person's history names it ("Corrected on approval – before: …").

**The person learns of it**. Rentalars reports approval,
correction – with the values before – and sending back – with the reason
– to the person as the notification "My times approved, corrected or sent
back", one message per person and action: if you approve twenty times of
one person at once, they get one.

**Reminder of approvals**. Whoever may approve times is
reminded of the submitted times and expenses waiting for their approval –
only of those they may approve, not of their own – with the notification
"Times waiting for my approval". By default this is on: daily at 8:00, the
first time one day after handing in, then every day as long as something
waits. It can be changed or switched off under Settings → Notifications,
"Times to approve" (section 16, "Notifications of the company").

Only approved times count towards billing by effort and towards the
comparison of planned and worked hours (section 12). An approval can be
taken back ("unlock" in the report); the entry is then submitted again.

**Recording for others** – the crew chief for their team – works with the
same special right.

Every change to a time entry is recorded in the person's history.

### My times

My area → **"My times"** tab: week by week your own entries with hours,
status and total; above them the running stopwatch and everything not yet
handed in. Open entries can be corrected or deleted via the pencil;
approved ones no longer.

- **Hourly pay**: between "Hours" and "Amount" you see your
  rate for this entry. For a deployment "per day" with your own day rate,
  it shows "Day rate" and its amount, once a day per deployment; further
  entries of the same day show "in the day rate". If your deployment has a
  **flat rate** for you, it shows "Flat rate" and its amount; it counts only once per deployment – with the first finished entry, in
  whatever week. Further entries of the same deployment show "in the flat
  rate" and count 0; the hours still count. A flat rate comes before a day
  rate. The weekly total counts what is shown there. Rentalars never shows the guide value of a job
  function as your pay. You only see the column and amounts if your
  company shows you your rates.
- **"Copy to the clipboard"** on approved times puts a text for your own
  invoicing on the clipboard – one block per job function of the period:

  ```
  Lighting technician
  	Date: 2026.10.16
  	Project: 2026-0042 - Stadtfest
  	Activity: Setup
  ```

  The first line is the name of the service product of the job function,
  indentation is with a tab; the date is the day of the start, "Activity"
  the phase of the deployment (otherwise empty). Rentalars confirms with
  "Copied".
- **Hint about the Companion app:** at the top there is a small hint that
  you can also record your times with the Rentalars Companion app for
  Android – with stopwatch, even without a connection; you create the
  access under My account → API tokens. With × you hide it for good.

### Report

The **"Report"** tab – under "Personnel" for everyone who may approve
times, otherwise under "My area": hours summed up by **person, project,
job function or day**, filtered by person, project, job function, period
and status. Without a filter it shows the current month.

- Everyone sees the report of their **own** times.
- Anyone who may approve times sees the times of others – for the projects
  they may see.
- **Amounts** appear only where you may see the hourly rates: with the
  special right all of them, otherwise your own. If a total would contain
  a hidden amount, it is left out altogether rather than appearing too
  small.

Below the totals, the individual entries are listed, page by page as in
any list; the totals always cover all of them. If entries have a hint
(above, "Hints at unusual times"), the page says how many; the tick
box **"Only entries with hints"** in the filter shows only them. "The entries" is a table like any list: columns, sorting, "Group by"
and CSV above the list belong to this list only; the **CSV** button at the
top provides the file of the report as before.

**CSV** provides the entries for the spreadsheet – with the last column
"Hints" –, **Timesheet (PDF)** the same selection for printing and
signing – one section per person with a signature line, the hints below
the entry. Both contain exactly what the page shows, so without a filter
the current month.

> **Many people at once.** A timesheet for everyone takes patience:
> Rentalars builds a month with 100 people (78 pages) in about 20 seconds.
> It refuses more than 3,000 entries in one timesheet and asks you to
> narrow down by person, project or period. This limit does not apply to
> the CSV file.

### Expenses and travel costs

Meals on the road, the trip in your own car, the hotel, parking and
tolls: each person records such outlays themselves, for the project they
arose for – best right away on site with the phone.

**Recording.** **"Record expenses"** is under My area → "My expenses", in
the overview of a project under "My expenses in this project" and in the
dialog after a recorded time. In the dialog:

1. **Project** – prefilled, as with the times, with the one you are
   currently planned in. Expenses always belong to a project; they cannot
   be booked on a closed or cancelled one.
2. **Kind** – Meals, Travel, Accommodation, Parking and tolls or Other –
   and **Day** (not in the future).
3. **Amount in euros** – or, for a **trip in your own car**, just the
   **Kilometres**: Rentalars calculates kilometres × rate per kilometre
   (€0.30 by default; the dialog states the rate). A trip keeps the rate
   it was recorded with. For a train ticket you enter the amount. Rentalars deducts the way to work (below).
4. **Note** – what it was, for example "Lager – Stadthalle und zurück"
   (warehouse – town hall and back) – and the **Receipt**: on the phone
   photographed straight away with the camera, otherwise a photo or a PDF
   file. Rentalars turns photos the right way round, makes them smaller
   and in doing so removes all details of the camera – only the place of the shot stays.
5. **"Hand in for approval right away"** is ticked; without the tick the
   expenses stay with you until you hand them in under "My expenses".

Anyone who may approve times can also record expenses for others and
first chooses the person in the dialog.

**Way to work**. Everyone travels from home to the company
and back anyway; that is not an outlay. If the **"Distance home – company
(km)"** is entered for a person under Personnel (section 12, "People"),
Rentalars deducts **twice the distance once a day per project** from trips
by kilometres – there and back. If someone lives 14 km from the company, a
trip of 42 km is calculated like this: "42 km − 28 km way to work = 14 km"
– that is exactly what the trip shows, and only the 14 km are paid.

- Several trips on the same day for the same project share the deduction,
  in the order in which they were recorded. A trip that is shorter than
  the remaining way to work stays recorded with €0.00.
- Without an entered distance nothing is deducted; nor for trips with an
  amount instead of kilometres (train ticket).
- What a trip had deducted stays stored on it. It is recalculated only if
  you change its project, kind, day or kilometres.
- Under Settings → Company data and settings, **"Deduct the way to
  work from trips"** switches the deduction off for everyone. Expenses
  already recorded do not change as a result.

**My expenses** shows your expenses month by month with kind, amount,
status and receipt, the total of the month and how much of it has been
reimbursed, as a CSV to download; at the top, under "Not handed in yet",
you see what is still with you or was sent back, with "Hand in all". As
long as expenses are not approved, you change them with the pencil or
delete them together with the receipt; approved ones are locked.

**Approving.** Submitted expenses are listed under Personnel → "Approve"
with their project below the times, ticked, with receipt – "Approve the
ticked" and "Send back the ticked" apply to both. As with the times,
sending back requires a reason. The person gets a notification when their
expenses are sent back.

**Reimbursing and evaluating.** Personnel → **"Expenses"** tab – for
everyone who may approve times; anyone who sees only their own gets to
theirs via "My expenses" – shows per **month and person** the total, what
has been reimbursed and what is still to be reimbursed; below that the
individual expenses. You can filter by person, project, kind, period and
status – "To reimburse" means: approved and not yet marked as reimbursed.
Without a filter the page shows the current month. Once you have paid
out, tick the expenses, choose the day under **"Reimbursed on"** and press
**"Mark the ticked as reimbursed"**; the person is notified. "not
reimbursed" takes the mark back, "unlock" an approval. The individual
expenses are a table like any list (section 2, "Lists"). **"CSV with all
columns"** downloads the same selection with the usual columns, sorted by day, with the column "Way to work
deducted (km)" and as `spesen-<Datum>.csv` – that is the file for payroll
accounting; "CSV" only the columns shown.

**Costs of the project.** Approved expenses count towards the costs of the
project: the planning shows them below the totals as "Expenses and travel
costs (approved)", and they reduce the profit from the project – in the
project list too (section 8, "The totals"). The row is visible to those
who may see personnel costs. Expenses do not appear in the price overview
or on the documents for the customer; if you want to charge them on, plan
them as incidental costs (section 5).

---

## 14. Correspondence

*The mails of a project are visible to whoever may read the project and has
the special right "Read correspondence"; writing also needs "Write and send
correspondence". The role "Project management" has both, "Read only" has
reading, the crew has neither. Every message has a lock or is
open: messages with a lock are read only by those who may also "See prices
and calculation"; open ones are also read by the crew planned in the
project that has accepted or is planned firmly (below, "Messages with a
lock").*

### How mails get into the project

Rentalars reads along in one or more **mailboxes**, such as
`projekte@eure-firma.example` and `info@eure-firma.example` (below, "Setting up
mailboxes"). Every project has a **tag**, shown at the top of the project
page:

```
[RL#2026-0042]
```

If it appears in the **subject** of a mail – anywhere, however it is
written, even after "AW:" –, Rentalars fetches the mail into the
project on the next fetch, with all its attachments, whichever mailbox it is
in. This happens by itself every few minutes; "Fetch now" under
Settings → "Mailboxes and signature" is quicker.

So that customers use the tag, it is already in the subject of every mail
you write **from Rentalars**. When the customer replies, the reply comes back
by itself – even if they delete the tag from the subject, because Rentalars
recognises what it is a reply to.

A subproject has a tag of its own, such as `[RL#2026-0042-1]`; mails with it
land in the subproject. Likewise every service case has a tag made from its
number (section 7, "Service cases").

**Tags with the earlier number.** Mails sent out earlier carry
the project number with "P-", such as `[RL#P-2026-0042]`. If someone replies
to one, the reply still lands in the right project (section 7, "Creating a
project"). If you write back to such a mail from Rentalars, the subject gets
today's tag instead of the old one.

For mails you write outside Rentalars: copy the tag with a click and put it
in the subject. A mail that arrived without a tag gets into the project when
you forward it with the tag in the subject to a mailbox of the
correspondence – or, if its mailbox takes in mails without project tag,
through the inquiries (below).

**What Rentalars does not touch:** mails **without** a tag stay in the inbox
as they are – unread, not moved. Rentalars is not a mail program; you deal
with everything else as usual. If a mailbox is set to take in mails without
project tag, they also appear as **inquiries** under Projects – only mails that arrived from the moment set under "taken in from", and only
unread ones if you wish (below, "Setting up mailboxes"); even then they stay
in the inbox until someone takes them over. If a mailbox has several
addresses, this applies per address (below, "Further addresses of a
mailbox"). What happens in the mailbox to mails that were taken in is set
per mailbox: mark as read and move into a folder (by default "Rentalars", so
that the inbox stays tidy), only mark as read, delete, or leave unchanged in
the inbox.

**The crew's answers to deployment requests** carry a code of their own in
the subject, such as `[RA-E-…-JA]`. Rentalars recognises them in every
mailbox it fetches, enters the acceptance or refusal and then treats the
mail like an assigned one (section 12, "Answering deployment requests by
mail"). They do not appear in the Correspondence tab of a project.

### The "Correspondence" tab

All mails of the project, incoming and outgoing, in two views – switched at
the top right; Rentalars remembers your choice until you log out:

- **"List"** – the newest at the top: "sent" or "received", subject, sender
  or recipient, date, attachments.
- **"Conversation"** – the exchange in order of time, like a chat, the newest
  mail at the bottom: incoming on the left, sent on the right. Each mail
  shows only what is new in it; quoted earlier mails and the signature are
  folded away ("Show quoted text and signature").

In the **whole project**, the list also holds the mails of its subprojects –
those you may read –, each marked with the number of its subproject; a click
opens it in the subproject.

A click on the subject opens the mail. It appears **compact**: at the top, in
one line, sender, recipient, date and the number of attachments, and right
below it the text. A click on this line unfolds the details – From, To, CC,
BCC, date, subject and how the mail was assigned, also "as a new
service case" for a mail that became a service case straight away (below,
"Further addresses of a mailbox").

- **Text:** Rentalars shows the mail cleaned up in a frame of its own –
  without scripts, and **without pictures from other servers**: such pictures
  tell the sender when and where a mail was read. Above the text it says how
  many were held back; "Load them" shows them for this mail.
- Open or download **attachments**. **"To the project files"** puts an
  attachment with a document type into the files of the project ("Documents"
  tab) – the customer's stage plan, for example, which the crew then finds in
  the "Overview" tab.
- **Out-of-office replies** and **delivery failures** are marked. Rentalars
  never answers mails in a project by itself (only the crew get a
  confirmation of their answer to a deployment request, section 12); mails
  without project tag only if you have set up an automation for it
  (section 16, "Automations").
- **"Belongs to another project?"** Enter the project number, "Move mail".
  This is noted in the history of both projects.
- **"Belongs to a subrental?"** If the mail came from exactly one supplier of
  the project or went to them, Rentalars has already assigned it to that
  supplier's subrental; the details of the mail then name the supplier under
  "Subrental", with a link to the page "Subrental at …" (section 9,
  "Subrenting"). Here you choose another supplier of the project or "– to no
  subrental –".
- **"Remove"** takes the mail out of Rentalars; it stays in the folder of
  the mailbox.

If a mail arrived for a **finished or cancelled** project, it is still filed
there, with a note, and the project manager is told.

The Correspondence tab looks the same in a project and in a service case
and has the same buttons. **"Write mail"** appears there – and, on the page
of a service case, in the "Latest mails" box – if you may read and write
correspondence and a mailbox can send this mail; a service case also
sends through the mailbox of its address "only for service cases" when no
outgoing mailbox is set up (below, "Further addresses of a mailbox").

### Notes in the correspondence

Not everything happens by mail: the customer phones, something is agreed
at the warehouse counter. You record that on the
Correspondence tab – in a project as in a service case – with **"Add
note"**:

- **"When"** – when it happened; now by default. It may also have been
  earlier, never in the future.
- **"Subject"** – optional; empty, the first line of the note counts.
- **"Note"** – what was said or agreed.

"Save note". **Nothing is sent** – the note stands only in the
correspondence, at its time between the mails: in the "List" with the
label "note" and "noted by …", in the "Conversation" in the middle with a
dashed frame. The short overview counts notes separately ("2 notes"), and
the summary by the AI reads them too (below).

Whoever may write correspondence may write a note, also in a closed
project. Whoever wrote it or may edit the project may change or remove it
– on its page under **"Change note"** or with "Remove". It cannot be
answered. For the automations of a service case a note is no new
communication (section 16, "Automations"). Notes go with the mails after
the period under "keep mails for … days" (below, "Setting up mailboxes").

### Messages with a lock

Every message of the correspondence – mail or note – is **with
lock** or **open**. This lets you control whether the crew can read a message or only those
who see the finances:

| | read by |
|---|---|
| **with lock** | whoever may read the correspondence **and** has the special right "See prices and calculation" |
| **open** | whoever may read the correspondence – and in addition the **crew planned** in the project that has accepted or is planned firmly (read only), and whoever works on a service case (section 7, "Working on the case") |

Who may read the correspondence at all does not change (above, at the
start of the section). Whoever reads it without the price right sees only
the open messages; the list says so ("You see the open messages. …"). A
message you may not read does not exist for you – not in the list, not in
the mail thread, not in the search, not as a notification; its attachments
follow it. In the history of the project it appears without its subject:
"Message received on …", "Message sent on …" or "Note of …"; a message removed or moved to another project
is named with its subject only to those who also read the messages with a
lock. Notifications and open items from automations name a mail with a
lock only as "Mail from … (with lock)" or "Mail sent (with lock)", without
the subject (section 16, "Automations"). Whoever has accepted in the project or is planned firmly
therefore gets the tab "Correspondence", with the open
messages for reading; someone planned but not asked yet, not answered yet
or declined sees the overview as before, but no correspondence. The crew cannot
write, answer or add notes there.

**How new messages start.** Under **Settings → Mailboxes and signature**,
with the "Rules for all mailboxes" under **"Lock of new messages"**:

- **"New messages in projects: with lock"** – on by default:
  correspondence in projects is confidential.
- **"New messages in service cases: with lock"** – off by default: whoever
  works on the service case reads them, also without the price right.

This holds for mails that come in, mails and notes written, inquiries
taken over and a service case made from a mail. The exception: an **answer
to a message with a lock** starts with the lock – it quotes that message;
through the API too, when the program leaves out `locked` –,
and a mail coming in that answers a message with a lock of the same project
is stored with the lock. A mail moved to another project keeps its lock.

**Putting the lock on and taking it off** is for whoever may write
correspondence and sees prices. When writing a mail, an answer or a note
there is the tick box **"With lock"**, ticked as the setting for projects
or service cases says – always for an answer to a message with a lock.
In the list a message with a lock carries the lock sign, next to it
**"Take the lock off"** – or **"Put a lock on"** for an open one; the page
of a message says who reads it ("With lock: only those who may see prices
and calculation read this message." or "Open: the crew of the project
reads this message as well."), with the same button.
Whoever writes correspondence but does not see prices writes open
messages – with a lock they could no longer read their own; the form says
so.

**When the lock is taken off**, the crew planned in (accepted or planned
firmly) that could not read the message before learns of it – once per message and person, as the
notification "New message for the crew of …" of the kind "new mail for a
project". Notifications about a new mail go only to those who may read it
anyway.

**Existing messages:** all existing messages in projects got
the lock, those in service cases stayed open. So what was visible before
is visible now; the crew reads existing messages only once someone takes
the lock off.

### Summary and short overview

Above the correspondence – the same in a project and in a service case –
is the **Summary** box. If there is a summary by
the AI, it is at the top in a line with "made by AI" and its date. It is folded when the page opens; a click on the line unfolds it.
It is open only right after it has been written. Below it the **short
overview without AI** is folded as well.

**The short overview without AI** is always there, even if no AI is set up
at your company: who is involved, how many mails (received and sent) and
notes, the first and the last, who wrote last – with the note "received –
not answered yet" if the last mail came from outside –, dates and amounts
mentioned, open questions from the newest mails and the attachments.
Rentalars looks for dates, amounts and questions in the newest 200 mails.

**"Summarise"** is there if your company has switched on summaries with AI
(section 16, "AI"); otherwise the block says who can switch them on. The
AI reads the notes (above) too; with **"Include the chat"** the project's
chat is added. If a chat message is deleted later, the summaries that read
the chat after it was written disappear (section 7, "Chat in the project").
The summary is written
in the background – you can go on working and get a notification when it
is done. It is marked **"made by AI"**, with model and date, and written in
your language. If a new mail arrives afterwards, it says **"out of date"**
– then "Summarise again". If the summary was made **with the
chat**, a new chat message makes it "out of date" too; changing an earlier
chat message does not. If a mail it covers is deleted, the summary goes
too.

The block says before "Summarise" roughly how long it will
take – measured on your server. If it takes long (more than five
minutes), Rentalars says so; you can still start it and go on working.
While the AI works, you see what it is doing ("reads the mails …",
"writes … 120 words"). It is only stopped when the AI writes nothing at
all for a longer time – not after a fixed total time.

- **AI can be wrong.** Check important details – dates, amounts,
  commitments – in the mails themselves.
- **Where the mails go:** with the local AI they do not leave the server.
  If your company has chosen another interface for summaries, the block
  names it before you click "Summarise". On a Raspberry Pi a summary takes
  a few minutes.
- **Who sees it:** whoever may read the correspondence may read and start
  a summary. If, for a whole project, it also covers subprojects whose
  mails you may not read, you do not see it. Since the AI reads every
  message, also those with a lock, summary and reply draft are only for
  those who may read all messages (above, "Messages with a
  lock").

#### Automatic summaries at night

The summary can also be written **by itself, at night**,
for projects and service cases whose correspondence has changed – the same
summary as the button "Summarise", marked **"created automatically"**
(and "Created automatically at night." in the line below it). It is
**off until an administrator opts in** (section 16, "AI"): without that,
Rentalars sends not a single mail to a model by itself.

**What you see.** In the summary box nothing changes except the badge. If
the summary is "out of date" and the automatic summaries are on, the
note adds "It is renewed automatically at night, or press “Summarise
again” now." Under the summary the box lists the **earlier summaries**
("2 earlier summaries"), each with date, model, provider and "created
automatically" or "made on request"; Rentalars keeps the last five by
default. The line under a summary also says whether it was made with the
chat and whether **"Messages with lock were not read."**, and how many
older entries were left out because the text was too long.

**Keeping a project or customer out.** Whoever may edit the project has the
button **"No automatic summaries for this project"** in the box; whoever
may change customers has **"No automatic summaries for any project of
this customer"**. The box then shows "excluded" or "customer excluded";
"Allow automatic summaries for this project again" (or "… for this
customer again") undoes it. Use it for a customer who has not agreed to
the processing, or for a project whose mails you do not want to hand to
a model. Summaries by hand still work. When a customer is anonymised
(section 6), their automatic and earlier summaries are deleted and none is
made again.

**What decides whether a project is summarised.** The job asks, for every
project in the chosen statuses that is not excluded, only one thing: did
the correspondence change since the stored summary – a different number of
mails, a newer mail, and, if the job reads the chat, a newer chat message?
Planning, tasks, times and documents are not in the text the model gets;
changing them costs no call. If the texts the model would get are the same
as before (for example a new mail with a lock that the job may not read),
nothing is sent. Fewer mails than the "least number of mails" (2 at first)
are not summarised, and a project that was summarised less than "least
time between two summaries in hours" (20 at first) ago waits.

**Who may read the result.** The job has no user of its own; it acts as
"system:ai-summaries". Who sees the summary is decided by the same rights
as for a summary by hand: for a whole project it also covers the
subprojects, and whoever may not read all of them does not see it. Since
the job reads messages with a lock by default (in a project every message
starts with the lock), the summary is shown only to those who may read all
messages (above, "Messages with a lock"). The summary can be wrong, like
every other.

**For administrators: switching it on, honestly.** Before you opt in,
think about what it means for information security and the GDPR:

- **The data leave the server, unless the AI is local.** The page
  shows in red whether the provider of the summaries is a "cloud service
  – the data leave the company", "in the company network" or the "local AI
  on this server – nothing leaves it". With a cloud service, the texts of
  your customers' mails go to a third party **every night, without
  anyone pressing a button**. You need a data processing agreement with it
  and a place for it in your privacy statement; Rentalars cannot check
  that for you.
- **The notice before you switch on says what is sent**, built from your
  settings: the mails of the project and its parts (subject, text without
  quoted earlier mails, names of the senders); notes, chat, messages with
  lock and the names of attached files only if you allow them; and the
  number and name of the project. **Never sent:** prices, calculation and
  margins; personnel costs and times; contact and bank data of customers
  from the master data; files and their content; passwords, tokens and
  API keys.
- **Filters are not anonymisation.** Before sending, Rentalars takes out
  what has a recognisable shape – by default IBANs, card numbers, secrets
  such as passwords and tokens in links, e-mail addresses and phone
  numbers. **Names, street addresses, offers and everything said in plain
  words go along.** You choose the classes under "Taken out of every text
  before it goes to the AI"; what you untick is sent as it is, and if you
  untick all of them, the page says "Nothing is taken out: bank data,
  passwords and addresses in mails go to the provider as they are." This
  holds for summaries by hand too.
- **You agree to one server.** Switching on needs the tick "I have read
  what goes to the provider and agree"; Rentalars notes who agreed and
  when. The agreement holds for **the local AI, or for the server – address
  scheme, host and port – of the interface**, not for its name or model.
  Changing the name or the model of an interface does not matter; pointing
  it to another server, or switching from the local AI to a cloud
  service, stops the job ("stopped: other provider") until you confirm
  again.
- **The job is limited.** The window of the night (1:00 to 5:00 at first),
  "most summaries per night" (20), "token budget per night" (200,000;
  0 is no limit), the statuses of projects and service cases, and a stop
  after three failures in a row. A night in which the
  provider could not be reached is tried again, up to three attempts, 20
  minutes apart.
- **Everything is logged.** The calls appear in the log of the AI calls
  ("All calls") – never with their content –, and the list of **"Runs"**
  on the page shows when each run started, who started it by hand, how
  many were summarised, "Unchanged" or "Failed", and the tokens, with the
  error of a failed project (without any mail content).

*Limits:* the model's answer is shown as plain text, never as formatted
text. The nightly job makes summaries only, no reply drafts. A project
that fails is tried again the next night.

### Writing and answering

**"Write mail"** in the Correspondence tab, or **"Answer"** or **"Answer
all"** on a mail:

- **"To"** is filled in – for a new mail with the contact of the project, for
  "Answer" with the sender of the mail (for a sent mail: with its
  recipients). "Answer all" also takes all other recipients from To and CC,
  except your own mailboxes.
- Under **"To"** there are two buttons: **"Add crew"** enters everyone
  planned in the crew lines of the project – without declined requests and
  without people who have no e-mail address; in the whole project, the crew
  of the subprojects you may see is added. **"Add customer"** enters the
  contact of the project (in a subproject without one, that of the whole
  project), or, without a contact, the customer's address. What is already
  in the field is not added twice; next to it you see what was added ("Added
  to "To": …"). The page does not reload. If there is no address, the button
  is missing.
- You get the crew's addresses as in the overview: whoever may edit the
  project or see the personnel gets all of them; everyone else only those a
  person has shared with colleagues.
- **"CC"** and **"BCC"** – whoever is under BCC gets the mail without the
  other recipients seeing it.
- Separate several addresses with commas. From three letters on, Rentalars
  suggests **addresses** – from customers, contacts and personnel, as far as
  you may see them.
- The subject gets the tag by itself, an answer the quoted text and "Re:"
  before the subject – for those who use Rentalars in German, "AW:".
- **"Add the signature"** is ticked: the signature with your details goes
  below the text (below, "Signature"). For a short answer, untick it.

As the **sender**, the recipient sees your name and the company, such as
"Max Mustermann | Muster Veranstaltungstechnik", with an address of your
mailboxes. Preset is that of the mailbox that sends the correspondence
(outgoing, below), in a **service case** the address with the
role "only for service cases", if you have entered one (below, "Further
addresses of a mailbox").

**Choosing the sender**. If you may send with more than one
address, the form has **"Sender"**: the mailboxes of the correspondence
that can send, and their further addresses. The preset address is open to
everyone who may write correspondence; every other one only to whoever has
a role ticked for it under **"May send from this address"** (below,
"Setting up mailboxes"). When **answering**, the address the mail came in
through is preselected, if you may use it. The mail is sent through the
mailbox of the chosen address and carries its signature (below,
"Signature") – the preview changes along. At the top of the form it then
says "Sent as …". Answers thus always come back into a mailbox of the
correspondence and so into the project.

You can attach:

- **files of the project** (tick boxes),
- under **"Documents"**: **packing list**, **price overview** and **deployment
  overview** as PDF, freshly made – the price overview only with the right
  to see prices –, and the created **documents** of the project
  (section 11), for invoices also the XRechnung; documents with prices only
  with the right to see prices. The deployment overview in the mail is what
  any colleague sees: without "My deployment", the crew's phone and e-mail
  only as far as shared – the mail leaves the company. It is not ticked by
  itself,
- **further files** from your computer.

"Send" sends the mail through the mailbox of the sender and files it in
the project, with everything attached. If a created document went with it,
Rentalars notes on it when and to whom.

"Send" next to a document in the Documents tab leads straight here, with the
document already ticked.

**Suggest a draft.** If your company has switched on reply drafts
(section 16, "AI"), "Write mail" has the button **"Suggest a draft"**: the
AI writes a reply from the mails so far. That takes a moment; only you see
the **"Draft by AI"**. **"Take it over into the text"** puts it above the
quoted mail, "Suggest another draft" tries again. Check and change it
before you send – only what you send yourself goes out. You need the right
to write correspondence for this.

### Inquiries

**Projects → "Inquiries" tab** – for everyone who may read the module
E-mail; whoever has only the module E-mail gets straight here through
"Projects" in the sidebar. Two kinds of mail wait here:

- mails with a **tag for which there is no project** – a typo, an old
  number –, with their tag;
- from mailboxes that take in mails without project tag (below), mails
  **without a tag**, marked "without tag" – such as the inquiry of a new
  customer to `info@`.

A **defect report** can also wait here – if the automation for
defect reports does not make it a service case at once but puts it "under
Projects → Inquiries" (section 16, "Automations"). It carries the label
"defect report", its subject leads to the item, and under "Filter" you
find all of them with **"Kind: defect report"**. A defect report is not a
mail: there is no taking over and no "As a project" for it, only **"As a
service case"** (section 7, "Service cases") or the bin.

**Noting inquiries by hand**. Not every inquiry comes by
mail. If somebody calls, you note it with **"Add inquiry"** at the top of
the page, so that the office can deal with it:

- under "Who and when": **"When"** (now by default, never in the future),
  **"Who"**, **"Phone"**, **"E-mail address"** and, if you like, the
  **"Customer"** – type and choose from the suggestions;
- under "What it is about": **"Subject"** and **"Note"** – what was asked
  or agreed.

It needs something to get back to somebody (who, phone, e-mail address or
customer) and something it is about (subject or note); "Note inquiry". In
the list it carries the badge **"Noted"**, with phone, e-mail address and
customer below the name. Under "Filter" you find all of them with
**"Kind: noted by hand"**; the search also finds phone, note and customer.
**"Edit"** changes it ("Save inquiry"), and there **"Delete inquiry"**
deletes it for good – the bin in the list only takes it off the list.
**"Take over"**, **"As a project"** and **"As a service case"** work as
for a mail; the new project or case is preset with customer and subject,
and the inquiry becomes a **note** in its correspondence (above, "Notes in
the correspondence") – with who, phone, e-mail address and customer,
written by whoever noted it. No mailbox is needed for this, and the
automations for incoming mails do not run. Whoever may edit in the module
E-mail may note inquiries; whoever noted one may also change and delete
it.

The inquiries are a **table** like every list (section 2,
"Lists"): with subject, sender, date, tag and mailbox, columns to choose,
sorting by clicking the heading, filters by text, kind and mailbox, "CSV" and
"CSV with all columns", and **"Group by"** sender, date, tag, mailbox or to
address. The column **"To address"** (under "Columns") names the address of
the mailbox the mail went to – for a mailbox with several addresses, the one
it was written to; older mails have none
("(no entry)" when grouping). All mails stay unchanged in the inbox until
someone takes them over.

- **Assigning to a project:** enter the project number and **"Take over"** –
  Rentalars fetches the mail from its mailbox into the project. While you
  type, the field suggests matching projects, with number and name, even if
  you type part of the name; only what you may see is suggested.
- **"As a project"** on a mail without tag opens a new project,
  filled in with the subject as its name and with customer and contact from
  the sender, as far as Rentalars knows them. On saving, the mail goes into
  the new project – or, if something goes wrong, everything stays as it was.
- **"As a service case"** turns a fault, a question or a repair straight into
  a service case, with the mail in it (section 7, "Service cases").
- **The bin** ("remove from list") only removes the entry, without asking;
  the mail stays where it is. With the **tick boxes** in front of the rows
  you take several off at once: as soon as one is ticked, a bar appears
  below the list that stays at the bottom edge while you scroll, with the
  number of chosen entries, **"Remove chosen from the list"** (after a
  confirmation) and "Clear choice".

Taking over, creating and removing from the list is for whoever may edit in
the module E-mail; a new project or service case also needs the right to
create projects. If every new inquiry should get a confirmation of receipt
straight away, an administrator sets up an automation (section 16,
"Automations"). The buttons "Mail log" and "Mailboxes" lead into the
settings; you find the state of fetching and "Fetch now" there
(below).

### Setting up mailboxes

*Settings → E-mail → "Mailboxes and signature" (or "Mailboxes" in the
inquiries). Mailboxes and the rules for all mailboxes can be changed by
whoever may edit the module E-mail; mailboxes can be deleted by whoever may
delete in it – by default only administrators; the signature by whoever may
change the settings.*

The page lists all **mailboxes** with their roles and their state: active or
off, last successful fetch, last error. **"Fetch now"** fetches all mailboxes
of the correspondence; **"Check connection"** logs in to IMAP and SMTP
without changing or sending anything. "Add mailbox" creates another one,
**"Edit"** opens one; "Check connection" and "Edit" sit side by side at the
same height in every row, on a phone too. An existing mailbox with any
provider is enough; it needs IMAP for fetching and SMTP for sending, both
encrypted. Every mailbox has:

- **Name** – shown in the list, in the mail log and in the inquiries – and
  **address**, with which sent mails appear to the recipient. As the name,
  who is writing and the company come first ("Max Mustermann | Firma").
- **Active** – switched off, it is neither fetched nor used for sending.
- **Roles:**
  - **Correspondence** – new mails are fetched and assigned to their project
    by the tag; several mailboxes can have this role.
  - **"sends the correspondence"** – mails written in projects go out
    through this mailbox, unless somebody chooses another sender (above,
    "Writing and answering"). This is exactly one of the active mailboxes of the
    correspondence; if you set it on another one, the previous one gives up
    the role, and the page says so.
  - **System mails** – invitations, password links and notifications go out
    through this mailbox; at most one. Without one, they go through the mail
    server from the configuration of the installation – and if none is
    entered there, not at all (below, "Without a mail server"). Every system
    mail ends with a note that Rentalars sent it (below, "Signature").

  A mailbox may have several roles – a single one for everything works too.
- **"Receiving (IMAP)":** server, port, encryption (SSL/TLS or STARTTLS),
  user, password and **"inbox folder"** (usually "INBOX"). For mailboxes of
  the correspondence also:
  - **"take in mails without project tag"** – switched on, they appear as
    inquiries under Projects (above); switched off (the default), they stay
    untouched in the inbox. This applies to the address of the mailbox and
    every address not listed under "Further addresses (aliases)" (below).
  - **"taken in from"** – taking in only works from a moment
    on: when you switch it on, Rentalars sets "taken in from" to that moment.
    Older mails stay unchanged in the inbox. You can change the moment, for
    example a few days back. What counts is when the mail arrived in the
    mailbox. If you switch taking in off, the field is empty again; the next
    time you switch it on, that moment applies again.
  - **"only unread mails"** – Rentalars only takes in mails
    that have not yet been read in the mailbox.

    In the list of mailboxes both appear after the rule, such as "from
    01/03/2027 08:00, only unread ones". Neither affects mails with a project
    tag or replies to assigned mails; they always go to their project. Why a
    mail was left lying is noted in the mail log ("arrived before the moment
    from which mails without tag are taken in" or "already read – …").
    Inquiries already taken in stay.
  - **"assigned mails in the mailbox"**: mark as read and move into a folder
    (by default "Rentalars"; Rentalars creates it if it does not exist),
    **"only mark as read"** (the mail stays read in the inbox,
    except the answer to a deployment request, which is moved to
    the folder as well),
    **"delete"** – only if Rentalars is the only place where they are kept –
    or **"leave unchanged in the inbox"**, unread too.
- **"Sending (SMTP)":** server, port, encryption. The tick **"same user and
  password as for receiving (IMAP)"** is set by default – then sending needs
  no access data of its own. If you untick it, separate fields for the user
  and password for sending appear; if the user stays empty, Rentalars sends
  without logging in.
- **"May send from this address"** – the roles whose members
  may choose this mailbox's address under "Sender" when writing (above,
  "Writing and answering"). The mailbox that sends the correspondence – in
  a service case the address "only for service cases" – is open anyway to
  everyone who may write correspondence; without a ticked role, every other
  address is open only to accounts with "has all rights".
- **"Signature"** (on the mailbox's page) – a signature of its
  own for all mails from its addresses (below, "Signature").

**"Rules for all mailboxes":** **"fetch every … minutes"** (default 2),
**"largest mail (MB)"** (25 MB; of larger ones Rentalars takes the text, the
attachments stay in the mailbox) and **"keep mails for … days"** (0:
unlimited), under **"Lock of new messages"** whether new
messages in projects and in service cases start with a lock (by default:
in projects yes, in service cases no; above, "Messages with a lock"); "Save
rules". Below it says how deployment requests are answered
("Answer to deployment requests: "Both".") and to which mailbox answers by
mail go. This is chosen under Settings → Company
data and settings; the link "Change under Company data and settings" leads
there (section 12, "Answering deployment requests by mail").

Rentalars stores passwords encrypted and never shows them again; an empty
field keeps the stored one. If a mailbox gets stuck, the others are still
fetched, and the administrators get a notification with the name of the
mailbox – one, not one for every attempt.

**Mail servers in your own network.** Rentalars connects to an
IMAP or SMTP server that leads into the internal network – this computer,
private networks such as 192.168.x.x, the server itself – only if the
operator allows it in the configuration file (`[network] allow_internal`).
Otherwise "Check connection" reports "The address leads into an internal
network …", and the self-check names the mailbox (section 16,
"Self-check").

#### Further addresses of a mailbox

Often the mails of several addresses arrive in **one** mailbox, such as
`support@` and `projekt@` as aliases of `info@`. You enter them
under Settings → Mailboxes and signature → "Edit" on the mailbox under
**"Further addresses (aliases)"**, each with a rule of its own:

- **Address** – as the mails are addressed to it; upper and lower case do
  not matter.
- **"Mails without project tag":**
  - **"do not take in"** – they stay untouched in the inbox;
  - **"as an inquiry"** (the default) – they wait under Projects →
    Inquiries;
  - **"create a service case at once"** – Rentalars immediately creates a
    service case with the mail (section 7, "Service cases") and notifies the
    person you enter under **"responsible for new service cases"**; they are
    then in charge of the case.
- **"taken in from"** and **"only unread mails"** – as for the
  mailbox (above): an address that takes in mails as an inquiry or as a
  service case only takes in mails from this moment on and, if you wish,
  only unread ones. If you choose one of these rules, Rentalars sets the
  moment to now.
- **"only for service cases"** – mails you write in a service case go out
  with this address as the sender (otherwise with the address of the
  outgoing mailbox); it is preselected there under "Sender".
  Only one address can have this role; if you give it to another one, the
  previous one loses it, and the page says so.
- **"May send from this address"** – as for the mailbox
  (above): which roles may choose this address when writing. It is sent
  through the mailbox of the address, or through the outgoing mailbox if
  that one cannot send; the list of addresses names the roles ("Sender
  for: …").

Mails **with** a project tag and replies to assigned mails always go to
their project or service case, whichever address they were sent to.
Rentalars reads which address a mail went to from the headers Delivered-To,
X-Original-To, To and CC, in this order; the first listed address found
there decides. Mails to addresses that are not on the list – including the
address of the mailbox itself – follow the mailbox's setting "take in mails
without project tag". If you put the address of the mailbox itself on the
list, its rule applies instead of this setting – for every mail that matches
no other listed address. (Many mail servers write the address of the
mailbox into Delivered-To even for a mail to an alias; that is why Rentalars
checks it last.)

A confirmation of receipt from an automation (section 16, "Automations")
goes out from the address the mail was written to. "Answer all" leaves out
your own addresses, and automations never answer to them. Changes to the
addresses are noted in the history of the mailbox.

#### Without a mail server

If there is no mailbox with the role "System mails" and no mail server in
the configuration of the installation, Rentalars **cannot send system
mails** – no invitations, password links, deployment requests by mail and
notifications by mail. The sender would then be `rentalars@localhost`, the
default of the configuration file, and nothing would arrive anywhere. Rentalars says so instead of reporting "sent":

- In the **mail log** such a mail is listed as **"not sent – no mail server
  set up"**; it does not count as sent, and a notification does not count
  as sent by mail.
- Wherever you send something – the test mail of the self-check, an
  invitation when creating a user or a person, "Send link for setting a
  password", a deployment request –, the page shows "Not sent – no mail
  server set up." with a link to Settings → Mailboxes and signature.
  After creating a user without a mail server, Rentalars goes straight to
  their page, so that you can give them a one-time password (section 16,
  "Users").
- The page "Mailboxes and signature" and the mail log show a note at the
  top, and the **self-check** names the missing mail server under "E-mail"
  (section 16, "Self-check").

The remedy: give a mailbox the role "System mails" – or have the
administrator of the server enter a mail server in the configuration.

**Deleting a mailbox.** At the bottom of a mailbox's form, **"Delete
mailbox"** leads to a page that says under "What follows" what happens:

- The mails of the projects that came or went through the mailbox, and the
  entries in the mail log, stay and still name the mailbox – in the log
  with "(deleted)".
- Inquiries and mails with an unknown tag that wait in the mailbox disappear
  from Projects → Inquiries; on the server they stay in the mailbox.
- Afterwards no mailbox has its roles. Rentalars no longer fetches new mails
  in it; system mails, without another mailbox for them, go through the mail
  server from the configuration of the installation.
- If answers to deployment requests by mail go to this mailbox, answers to
  the requests sent so far no longer arrive.
- If it sends the correspondence, another mailbox of the correspondence
  takes that over: if there is only one that can send, the page names it; if
  there are several, you choose under "Sends the correspondence from now
  on". If none can send, the mailbox cannot be deleted – first enter an SMTP
  server and address for another one, or switch the others off.

Instead of deleting, you can also **"Only switch off"** the mailbox there:
it stays in the list and can be switched on again.

The **prefix** of the tag – "RL" in `[RL#2026-0042]` – is set under
Settings → Company data and settings. If you change it, answers to
older mails still need the old one. (It has nothing to do with the prefix of
the project numbers; that belongs to the number, section 16, "Number
ranges".)

### Signature

A **shared signature for everyone** is on the same page (Settings →
E-mail, section "Signature") – with a preview of how it looks with your
details. **"Write signature"** or **"Edit signature"** opens the editor; it
can be changed by whoever may change the settings.

- The signature is **plain text or HTML**. Without HTML tags the line breaks
  are kept; with HTML, links, bold text, tables and pictures from a web
  address are possible. Rentalars removes scripts and forms.
- **Placeholders** fill in the details of whoever writes the mail – from
  their person in the personnel (section 12) –, and the company name from
  the company data: `{first_name}`, `{last_name}`, `{position}`, `{email}`,
  `{phone}`, `{company}`. The German names `{vorname}`, `{nachname}`,
  `{telefon}` and `{firma}` work too. A click on a placeholder in the list
  next to it inserts it at the cursor.
- **"Show preview"** shows it with your details; while you type, the preview
  follows by itself. "Save".

For example:

```
Best regards
{first_name} {last_name}
{position}
{company} · Phone {phone} · {email}
```

Rentalars adds it to every mail you write from a project; when writing, you
can leave it out with "Add the signature". Mails with a signature go out as
text and as HTML. Without a signature, mails go out with their text only.

**Signature per mailbox**. A mailbox can have a signature of
its own – `support@` with the hotline number, say. On the mailbox's page
(Settings → "Mailboxes and signature" → "Edit"), the button **"Write a
signature of its own"** or **"Edit signature of the mailbox"** in the box
**"Signature"** opens the same editor with the same placeholders. Mails
from the addresses of this mailbox – its own and its further ones – then
carry its signature; if it stays empty, the common one applies. Which
mailbox has which is shown on the page "Mailboxes and signature" under
**"Signatures of the mailboxes"** ("own signature" or "common signature").
Whoever may change the settings may change it.

**Mails Rentalars sends by itself** – notifications, invitations, password
links, deployment requests and the confirmations of answers by mail,
messages about errors and background tasks, the test mail of the
self-check – carry no signature. Instead they end with the sentence "This
message was sent automatically by Rentalars for Muster Veranstaltungstechnik:
https://rentalars.example.de" – with the company name from the company data
(section 16) and the address of your installation. That way every recipient
sees where the mail comes from. The address is set by the administrator of
the server. Mails you write in the project do not get this sentence.

### Mail log

**Settings → Mail log** (also through "Mail log" in the inquiries)
records every mail that arrived in a mailbox of the correspondence or left
Rentalars – invitations, links for resetting the password and notifications
too: time, sender, recipient, subject, project, **mailbox** and **result** –
"inquiry" for mails without tag that landed in the inquiries, **"answer to a
deployment request"** with "acceptance" or "refusal" for the crew's answers
by mail (section 12) – and the kind **"automatic
reply"** for answers of an automation (section 16, "Automations"), the result **"not sent – no mail server set up"** for system mails that
did not go out for lack of a mail server (above, "Without a mail server").
If an answer of the crew was not taken over, the result is yellow and gives
the reason ("refusal – not taken over: answered already"). This way you can
find out whether a mail really went out or arrived. The log never stores
the text of a mail. If a mailbox has been deleted, it is shown with its name
and "(deleted)", such as "Info (deleted)"; searching for the name still
finds it.

You can filter by text (address, subject, project number, mailbox name),
**direction**, **kind**, **result** and period; like every list, the log is
also available as CSV. The entries are kept as long as the mails ("keep
mails for … days"), with unlimited keeping for one year. When a customer is
anonymised, their entries disappear too.

---

## 15. Planning and overview

*Calendar and timeline for everyone with access to projects – everyone sees
the projects they may see. Material utilisation and shortages for everyone
whose project rights apply to all projects; the personnel plan for personnel
management; the follow-ups for everyone with access to projects.*

The sidebar has the entry **Planning** for this, with six tabs in this
order: Calendar, Timeline, Material utilisation, Personnel plan, Shortages
and Follow-ups. A timeline for a single product, model, item
or person is also on their own page (sections 4, 5 and 12), and one for a
project with its phases and its crew in its schedule (section 7,
"Schedule").

Timeline, material utilisation and personnel plan share the same time view:
they first show **4 days** in hour columns. With **"Days"** and **"Weeks"**
you switch the view, with "‹ earlier", "today" or "this week" and
"later ›" you page through, and under "From" you choose the first day.
Rentalars remembers until you log out whether you chose days or weeks and
how many days – shared by all three tabs (below, "Timeline").

Service cases (section 7) have no period and so appear neither in the
calendar nor in the timeline, the material utilisation or the shortages.

### Calendar

The calendar opens with the **week**. At the top you choose the **view**:
**"Week"** or **"Month"**. Rentalars remembers your choice until you log
out.

**Phases and follow-ups**. Above the calendar you tick what
it shows besides the projects: **"Phases of the projects"** (on by
default, as before) and **"Follow-ups"** (off by default). A follow-up
appears in the week at its time, without a time in the "all day" strip,
in the month below its day – with number and note; a click opens the
project or service case. Only the follow-ups you also see under Planning →
Follow-ups are shown (below). The choice is part of the page's address
(`?phases=`, `?follow_ups=`) and stays until you log out; without
JavaScript "Apply" takes it over.

Next to the calendar – below it on a phone – there is a **legend**: which
colour is which status and what the symbols mean. Colour is never the only
sign; every entry also names its status in the text that a screen reader
reads out.

**Month.** The projects of a month, week by week, Monday first. A project
over several days is **one continuous bar** across its days, with a broad
edge in the colour of its status. At the end of the week the bar carries on
in the next row; an arrow at the edge shows that it continues or began
earlier. Below the bars are the phases of the day ("Setup · 2026-0042") –
also a phase outside the rental period, such as the site visit three weeks
before. If not all projects fit into a day, it shows **"+3"** – a click
opens the week, as does a click on the number of a day. "‹ February" and
"April ›" page through, "today" jumps back to the current month.

**Week.** An **hour grid** as in common calendar apps: one column per day,
Monday to Sunday, the hours from top to bottom, with calendar week and date
at the top ("Week 42").

- Whatever lasts a whole day or longer is in the **"all day"** strip at the
  top; if there are many, "Show all all-day entries" shows the rest, "Show
  fewer" folds them up again.
- Shorter projects and the **phases** (dashed, such as "Setup") are shown at
  their time of day – so you see what is loaded in the morning and taken
  down in the evening. Whatever runs at the same time is shown side by side.
- The view begins at 06:00 (or at the earliest entry of the day); you reach
  the night by scrolling. An orange line shows the current time.
- A click on an entry opens the project.
- On a phone you swipe sideways through the days.

"‹" and "›" page week by week, "this week" jumps back.

Cancelled projects are hidden in both views; "Show them too" brings them
back. A subproject is called "Bühne Marktplatz (Stadtfest)" on the bar; the
tooltip says "Part of 2026-0042 Stadtfest".

### Timeline

The projects as bars, one row per project, with a background in the colour
of their status as in the calendar, the phases dashed below. Good for seeing
where things get tight: whatever is stacked on top of each other runs at the
same time. Subprojects are indented directly below their whole project. A
phase outside the rental period – planning and meetings weeks before, the
follow-up work afterwards – is in the row of its project on its day; the
project also appears when only this phase falls into the period shown.

At the top you choose how far you look – the same in the material
utilisation and in the personnel plan:

- **"Days"** (the default) – with columns for the hours, when the time of
  day matters: when loading happens, when the setup begins. Under "Days" you
  choose 1 to 10 days, 4 by default. With one day every hour has its own
  column, with 2 and 3 days two hours each, with 4 and 5 days three each,
  from 6 days six each. If the screen is wide enough, fine lines
  separate every single hour, even when a column covers two, three or six
  hours – as soon as an hour is at least 8 pixels wide; with a window width
  of 1920 pixels up to about 7 days, with 1280 pixels up to 4 days. The
  fine hour lines sit exactly on the hours at every window width.
- **"Weeks"** – day by day over a few weeks, four by default (two in the
  material utilisation and the personnel plan), selectable under "Weeks"
  from one to twelve.

Rentalars remembers until you log out whether you chose days or weeks and
how many days; this applies to timeline, material utilisation and personnel
plan together. If you switch from "Weeks" to "Days", the number you last
chose is there, otherwise 4.

Every bar is placed exactly at its time, in the "Weeks" view too: a setup
from 14:00 to 20:00 fills only that part of the day, a phase over midnight
begins and ends at the right time instead of filling two whole days. What
lasts a whole day fills it as before.

"‹ earlier" and "later ›" jump by the period shown, "this week" or "today"
jump back; under "From" you choose the start. In the views with hours, the scroll bar reaches twice as far as before – two shown periods into
the past and two into the future –, and Rentalars loads the next or previous
period as soon as you scroll sideways to the end – without losing your
place. This applies to the timeline, material utilisation, personnel plan
and the timeline of the schedule. The names stay on the left meanwhile. The
chosen view and number of days or weeks are kept while paging.

**Bars and labels.** Every bar has a frame in its colour, so that even with
grey bars – an inquiry, say – you see on the grey background where it begins
and ends, in dark as in light mode; likewise phases, absences, blocked times
and the availability. Cancelled projects are pale and struck through. If
the label does not fit into the bar, it ends with "…" instead of running
over the next bar; when you point at it with the mouse, the whole text is in
the tooltip. This applies to all timelines – here, in the personnel plan, on
products, models, items and people and in the schedule of a project.

### Moving appointments in the timeline

The setup begins two hours later, the collection moves forward by a day: in
the **"Days"** view of Planning → Timeline and in the timeline of a
project's schedule (section 7) you drag a bar with the mouse to its new time:

- **the bar itself** – it moves with its length;
- **one of its ends** – that only changes the start or the end.

You can move the **rental period**, every **phase** and – in the schedule –
the **event**, there also the **deployments of the people** and
the **open places**. The times snap to steps of 15 minutes; while you drag, a
dashed frame shows the new times. An end that lies outside the columns
shown has no handle – page on or choose more days.

**With the keyboard:** select the bar with Tab, **←** and **→** move it by
15 minutes, with **Shift** only its end; Rentalars announces the new times.
**Enter** shows the consequences, **Escape** takes the move back. **In the
schedule**, a click on a bar also opens the same window, in which you type the
times; in Planning → Timeline a click leads to the project as before. On a
phone you do not drag – a finger scrolls the timeline; in the schedule, tap
the bar.

**Only the window saves.** After you let go, "Move …" opens with
**"Before"** and **"New"** and, below, what follows – for that, Rentalars
tries the move once without saving or sending anything:

- which crew lines move along and who is **asked again** (section 12,
  "Requests: acceptance or refusal"), and whether someone is already planned
  elsewhere at the new time;
- for a phase that then lies outside the rental period, the tick **"Extend
  the rental period to …"** (not ticked) with a preview of whether material
  would then be missing – without the tick only the phase moves;
- for the rental period, how many lines take on the new one, which
  subprojects move along and whether **material is missing** afterwards
  ("With the new rental period 2 piece is missing.");
- for the deployment of a person in the schedule the planned
  hours before and after, whether the person is asked again, and – if they
  are the only one of their phase – the ticked box **"Move the phase “…”
  along"**, otherwise possibly **"Move the open places as … along"**, each
  with the reason; without the tick only the deployment moves (section 7,
  "Dragging people in the timeline").

If you drag the **whole rental period** (keeping its length), **"Move the
event, the phases and the crew along"** is ticked – the vehicle
bookings of the logistics move along with it (section 7, "Logistics").
Untick it if only the rental period should move; vehicle bookings with the
project's period follow it all the same. If you change only one end of the rental period,
only that end changes. Everybody scheduled for the project hears of the new
rental period – each person **once**: whoever has deployments
of their own moved along gets one message with all changed deployments
(section 12, "Messages about the deployment") and then not "new period …"
as well; the rest of the crew gets only the latter. **"Move"** saves,
"Cancel" leaves everything as it was;
afterwards the page reloads and is back on the bar.

Whoever may edit the project can move things, and only while it is not
finished. Phases of the kind "Planning and meetings" never ask about the
rental period (section 7, "Phase outside the rental period"). You drag the deployments of individual people in the same way in the
personnel plan (below, "Personnel plan") – there nothing ever goes along –
and in the timeline of the schedule, where the phase or open
places may go along.

### Material utilisation

How much of a product is reserved: choose a category or search by name or article
number. While you type, Rentalars suggests matching products with stock;
pick one with a click or with the arrow keys and Enter, and the page shows
exactly this product. If you close the suggestions with Esc and press
Enter, it shows all products whose name or article number contains the
text. If you then choose a category, it shows the whole category again.

The time view is the same as in the timeline and in the personnel plan:
first 4 days in hour columns, with "Days" 1 to 10 days, with "Weeks" one to
twelve weeks day by day (above, "Timeline").

Each column – hours or a day – shows how many pieces are firmly reserved at
most during that time, with "+2" for what options reserve on top. Adjacent
columns with the same numbers are merged into one field; when you point at
it with the mouse, you see the period. The colour says how tight it is:

| Colour | Meaning |
|---|---|
| green | reserved, there is still room |
| yellow | 80 % and more, or options beyond the stock |
| red | more reserved than there is |

**Kits** are listed too. Their row counts complete kits:
how many are **free**, in small print beside it with "−2" what options
would still take of them – as the timeline of a product does. Below the
name it says how many complete kits there are. The arrow in front of the
name unfolds the components, each with "2 ×" – so many pieces make one
kit – and their own utilisation; so you see which component gets tight.
This works without JavaScript too.

On a product's page, "Show in the material utilization" leads straight
here, with the product and the chosen period (section 5, "Stock and
availability of a product").

The calculation is the same as everywhere (section 9) – across all projects,
including those you cannot otherwise open. That is why the page is only
there for project rights that apply to all projects, and only
with the special right "See availability of material". Vehicles and trailers
are not shown here but under Material management → Fleet → "Utilization of
the fleet" (section 4, "Fleet").

### Shortages

The page from section 9, "The "Shortages" page".

### Personnel plan

One row per person, first over 4 days with hour columns, as in the timeline
over 1 to 10 days or over one to twelve weeks; deployments, availability and
absences are placed exactly at their time of day. Every row has two strips:

- **at the top, the availability:** what the person has entered in their
  availability calendar – all **hatched**, so that it is clear
  these are availabilities: green available, yellow with limits, red not
  available, including busy times from their linked calendars (section 12) –
  and, hatched in grey, their **absences**;
- **below, the deployments** as bars (project number and job function), with
  a coloured background and a broad colour stripe on the left: **orange**
  firm (the project is confirmed – also on the road, back in the warehouse
  or finished), **yellow** option, **grey** project inquiry. If the person
  has been **requested** and has not answered yet, the bar is paler and the
  stripe dashed. A click opens the project. For a subproject, the tooltip
  also names the whole project ("Bühne Marktplatz (Stadtfest)").

**Exact times.** When you point at a bar with the mouse – deployment,
availability or absence –, it gives the exact times, such as "Wed 10/03,
09:00 to 13:30", "… to 24:00" or "Wed 10/03, all day". A screen reader reads
out the same.

If someone is **planned twice**, **during an absence** or **although "not
available"**, there is a red **!** at the name, and the
**deployment** concerned is **filled red** – no other kind in the plan is
filled red, so it stands out at once and is easy to tell apart from "not
available" (hatched red). The coloured stripe at the start of the bar keeps
the colour of firm, option or inquiry. Availabilities and absences are not
filled; their hover says "conflict". The real times of day are compared: a
deployment in the morning and one in the evening of the same day are not a
double booking. "With limits" is visible but not a warning. The legend below
the plan explains the colours. The week of the availability calendar and
the timeline of a person (section 12) show the same red filling.

**Moving deployments**. In the **"Days"** view you drag a
deployment like the phases in the timeline (above, "Moving appointments in
the timeline") to another time, or make it longer or shorter at one end – in
steps of 15 minutes, with the keyboard using ← and → (with Shift only the
end). Beforehand the window shows the old and new times, the planned hours
before and after, whether the person is asked again and whether there are
overlaps at the new times. Only **"Move"** saves – like a change in the
dialog of the crew line: the planned hours move along if they were the
suggested ones, and whoever was requested or had accepted is asked again
(if set up that way). The phase and the project keep their times – that
they go along exists only in the timeline of the schedule
(section 7, "Dragging people in the timeline"). Whoever
may edit the project can move deployments while it is not finished; a
deployment cannot be dragged onto another person.

The plan holds all active people – office accounts without a job function
too. With the tick **"Only people with deployments or absences"**, only
those who are planned or absent in the period shown remain.

### Follow-ups

**Follow-ups** is the last tab of Planning – for everyone who
may read projects. It shows all projects and service cases with a follow-up
(section 7, "Follow-up") as a table: **"Day"**, **"Time"**, **"For"**,
**"Note"**, **"Project"**, **"Kind"** (project or service case) and
**"Status"**; you show "Customer" and "Responsible" under "Columns". You can
filter by "For" (everybody or for me), **"Only due ones"**, **"Also the
backlog"** (service cases in the backlog whose follow-up is
not due yet; without the tick they are left out) and a period (From,
Until). Like every list, it can be sorted, grouped by day, for or
kind, and downloaded as CSV (section 2, "Lists").

**"Move"** opens the dialog of the follow-up, in which you change the day,
time, person or note, and then returns to the table; **"Done"** takes the
follow-up off the project – as in the project itself. Both are only there
for projects you may edit.

Whoever may see the customers sees the follow-ups of all projects they may
see here; everyone else – the crew, for instance – only their own. "All my
follow-ups" on the start page leads here, already filtered to "for me".

### Notifications

The **bell** shows how many unread notifications you have; a click leads to
the list. Opening a notification takes you to where something happened and
marks it as read. "Mark all as read" tidies up.

What Rentalars notifies you about – in each case only what concerns you and
what you may see. Every kind belongs to a **category**:
**"Project"** (what happens in projects and service cases), **"Personnel"**
(what concerns you as a member of staff), **"Material"** (the warehouse) and
**"System"** (the running of the installation). They are listed in this
order in the notification settings too:

| Kind | Who | By e-mail by default | In the app by default |
|---|---|---|---|
| **Project** | | | |
| "Deployment request" – with answers by mail, as a mail with the buttons "Accept" and "Decline"; after changed times as a new request with the old and new times (section 12) | the person requested | yes | yes |
| "Answer to a deployment request" | whoever asked, the project manager | yes | no |
| "Price offer of a freelancer" – an offer, a counter-offer, taking an offer back, the answer to a counter-offer; with the amount, so only for those who see personnel costs (section 12, "Price offers of freelancers") | whoever asked, the project manager and the personnel planners – as far as they have the right "See hourly rates and personnel costs" and may read the project | yes | no |
| "Answer to my price offer" – accepted, rejected, countered, counter-offer taken back | the freelancer | yes | no |
| "Change of my deployment" – planned firmly, times, meeting point, note, phase, job function or vehicle changed (with the value before), taken off; one message per action (section 12, "Messages about the deployment") | the planned person | yes | yes |
| "Mentioned in a project chat" (section 7, "Chat in the project") | whoever was mentioned with @ | yes | yes |
| "Follow-up of a project" – on the day, from 06:00 or from its time (section 7, "Follow-up") | whoever the follow-up is for; if that person is deactivated, the project manager | yes | yes |
| "New mail for a project" – also a service case that was created straight from a mail; also "New message for the crew of …" when somebody takes the lock off a message (section 14, "Messages with a lock") | the project manager; for a new service case, whoever is responsible for the address – only whoever may read the message; for a lock taken off, the crew planned that has accepted or is planned firmly | yes | no |
| "Change of a project" (status, period) – also that a service case is now with you or that you are involved in one | the project manager and members with "Edit"; for a new period or a cancellation also the crew planned; for a service case, whoever is newly responsible or involved | no | no |
| new shortage – when and how far ahead is set under Settings → Notifications (by default daily, four weeks); by default also the reminder of known shortages, one per project ("Still shortages in …") | the project manager – only with the special right "See availability of material" | yes | no |
| Invoice still to be written – for a closed project without an invoice, by default also for a done service case (section 11, "Invoices still to be written") | the project manager and whoever Settings → Notifications names under "Also remind" – only those who may see prices | yes | no |
| "Message of an automation" (section 16, "Automations") | whoever the automation names | yes | no |
| **Personnel** | | | |
| "My expenses sent back or reimbursed" (section 13) | the person whose expenses they are | yes | no |
| "My times approved, corrected or sent back" – with the values before or the reason (section 13, "Handing in and approving") | the person whose times they are | yes | no |
| "Times waiting for my approval" – at the time set under Settings → Notifications (section 13) | whoever may approve them, never for their own | yes | no |
| "Qualification expiring" – 60 days before | personnel planning and the person themselves | yes | no |
| **Material** | | | |
| "Defect reported" | the warehouse | yes | no |
| "Stock below the minimum" | the warehouse | yes | no |
| "Inspections due" – once a day, collected | the warehouse | yes | no |
| **System** | | | |
| "A task in the background is finished (e.g. AI summary, reply draft, reading an invoice, export)" – so named in the settings, as the first kind under "System"; also a handover to Lexware Office; also "Video for the chat of … failed" | whoever started it; for the immediate handover of a new invoice only if it fails, to whoever created the invoice; for a video, whoever sent it | no | no |
| "Problem fetching mails" – with the name of the mailbox | the administrators | yes | no |
| "Problem with my calendar" | the person themselves, if one of their linked calendars (with its name) or their CalDAV calendar has not worked for a while | yes | no |
| "Error of the application" – also: webhook switched off (section 16, "Webhooks") | the administrators (for a webhook, everyone who may change the settings) | yes | no |

"The warehouse" means everyone who may change material; "personnel
planning", everyone who may change personnel.

How you are notified is set under **My account → Notifications** per kind,
ordered by category, in three columns:

- **"In Rentalars"** – at the bell and in the list;
- **"By e-mail"** – as a mail as well;
- **"In the app"** – the companion app for Android shows the
  notification on your phone (section 2, "The Rentalars app for Android").
  This is the default for deployment requests, mentions in the chat and
  follow-ups – what concerns you directly and wants a quick answer – and
 for changes of your deployment, which you need on the way.

If you want a kind only in the app, it is already marked as read in
Rentalars – as with "by e-mail" only. If all three columns are off, there is
no notification for this kind. Every single kind can be set
this way – also whether Rentalars tells you when the AI has finished a
summary, a reply draft or reading an invoice: that is "A task in the
background is finished (e.g. AI summary, reply draft, reading an invoice,
export)", the first kind under "System". The setting existed before, only
without the AI in its name and as the last kind under "System". The
**list of notifications** is a table like
every list; under "Filters" you can also choose a category. The
text of a notification appears there and in the CSV file as plain text with
its line breaks;
likewise the description of a project template in its list. HTML tags are
left out, and spellings such as `&amp;` turn back into "&"; text in angle
brackets that is no tag stays, such as `Max <max@example.org>`. Without an
e-mail address on the account there are no mails. Rentalars does not tell
you about what you triggered yourself – except that a task in the
background is finished. Every notification by e-mail ends with a note that
Rentalars sent it for your company, and the address of your installation
(section 14, "Signature").

Notifications are kept for 180 days and then disappear by themselves; the
period is in the settings (section 16, "Retention periods").

---

## 16. Settings

*For administrators.*

The **Settings** page is divided into boxes by topic:

| Box | Contains |
|---|---|
| **Company** | Company data and settings (with the state of the route service), Number ranges, Labels (section 4, "Labels") |
| **Users and rights** | Users, Roles and Directory (LDAP) |
| **Processes** | Automations, Notifications, AI |
| **Projects and personnel** | Surcharges, Price offers of freelancers (section 12), Rental scales (section 5) and – with access to personnel – Job functions (section 12) |
| **E-mail** | Mailboxes and signature, Mail log (section 14) |
| **Documents and accounting** | Document templates, "Template texts in English or German" (section 11), Text blocks, with the right to see prices Accounting and Incoming invoices (section 11) |
| **Master data** | Categories and codes, Custom fields and Fieldsets (section 4, "Custom fields"), Tax rates, Units, Manufacturers, Suppliers, Storage locations, Document types, Inspection types, Audits (section 4, "Audits and to-dos"), Qualification types |
| **Import and export** | the imports you may start, and for each import the "Export in the import format" for everyone who may read the list; the full export is under "Backup" |
| **Interface for other programs** | API documentation – it opens in a new tab –, My API tokens, Webhooks |
| **Operation and security** | Self-check, Backup (with the "Readable export of all data"), Encryption, Server address and certificate, Change log, Security log, Access log |

Whatever you may not see is missing here too – such as the box "E-mail"
without the module E-mail.

### Users

**Personnel and users are one.** Every person in the personnel has a login,
and every account is a person (section 12, "People"). So usually you create
a **person** (Personnel → New person); their account is created along with
it, with the role "Crew" or "Freelancer". Here, under
**Settings → Users**, you hand out roles and rights and help with
logging in. First name, last name, e-mail address and "active" change in
both places at once.

**Settings → Users → "Invite user"** works too: username, e-mail
address, name, **language**, roles, "Send invitation". The account then
also appears in the personnel. The language – "As the installation",
Deutsch or English – sets how Rentalars speaks to the person; the
invitation already goes out in it, and the person can change it later
under My account (section 2). The new user gets an e-mail with a link and
sets their
password themselves – you never learn it. The link is valid for 72 hours; on
the user's page, "Send link for setting a password" sends a new one. Without
an e-mail address there is no invitation – then use the one-time password
(just below). If no mail server is set up, the invitation does not go out:
the page says "Not sent – no mail server set up.", takes you to the user's
page so that you can set a one-time password, and links to Settings →
Mailboxes and signature (section 14, "Without a mail server").

**One-time password.** For people without an e-mail address, or when the
invitation does not arrive: on the user's page, **"Set one-time
password"**. After a confirmation Rentalars shows a password made of four
groups of letters and digits – **only this one time**. Give it to the
person in person or on the phone, not by e-mail. At their next login they
first have to choose a password of their own ("Choose your password"); until
then they cannot get at anything else, not through the API either. A
previous password stops working once the one-time password is set. The
security log records who set a one-time password and when. It does not work
for deactivated accounts.

On the person's page, "Login" shows whether someone already has a password
and when they last logged in (section 12).

**Directory accounts**. If the company directory is switched
on (below, "Directory (LDAP)"), most accounts are created by the first
login and kept by the directory: their name, e-mail address and roles are
brought up to date at every login, they have no password of Rentalars,
and "Send link for setting a password" and "Set one-time password" are
missing on their page. Instead the page shows the box "Directory (LDAP)".
The tick **"local (emergency) account"** on the form takes an account out
of the hands of the directory: it logs in with its own password only. Mark
at least one administrator this way.

**Valid until.** For temporary staff booked only once: enter a date on the
account. After that day the account is deactivated by itself.

Users are not deleted here but **deactivated** ("Deactivate user" on their
page): the history should still show who did something. A deactivated user
can no longer log in, can no longer be planned as a person and can be
reactivated at any time. A person who never logged in and was never planned
can be deleted together with their account in the personnel (section 12).

"has all rights" is an emergency access that does not depend on roles. Hand
it out sparingly – the first administrator has it. An account with this
right cannot be anonymised.

**Data access at a glance**. The list of users has – like
Personnel → People – the optional columns "Finances", "Personnel data"
and "Customer data", computed from the roles of each account; "no access"
means the account cannot log in (section 12, "People").

### Roles and rights

A **role** bundles rights; a user can have several roles. Then the highest
right per module counts.

**Per module** there are four levels, each including the previous ones:

| Level | May |
|---|---|
| "no access" | the module does not appear |
| "read" | look |
| "create and edit" | change |
| "delete" | delete as well |

The modules are: Material, Products, Customers, Projects, Packing and issue,
Personnel, Time tracking, E-mail, Settings and Reports.
The reports (section 8) are for whoever may read this module, read every
project and see prices; the roles Administrator, Project management and
Read only have it from the start. The
module **E-mail** covers the inquiries under Projects (read; take over and
note by hand with "edit"), the mailboxes and the rules for all mailboxes
("edit"; deleting mailboxes with "delete"). Whoever has only the module
E-mail sees "Projects" with the inquiries in the sidebar. The signatures –
the common one and those of the mailboxes – can be changed by whoever may
edit the settings; the mail log is visible to whoever may read the
settings. Which address someone may send project mails from is decided by
the roles under "May send from this address" on each mailbox (section 14).
The **logistics** of a project is planned by whoever may edit it – or may
read it and edit material (section 7, "Logistics"). The **monthly
statement** of the service cases can be seen by whoever may read projects,
see prices and customers and read each of its cases; changed by whoever
may edit projects and each of its cases, a draft deleted by whoever may
delete in projects (section 7, "Monthly statement"). The **outgoing
documents** can be seen by whoever may see prices and read
every project; the menu entry **Accounting** appears for whoever may see
one of the two (section 11, "Outgoing documents"). The mails in the projects depend on the special rights for
correspondence. Surcharges and automations belong to the module
**Settings**: read to look at them, edit to change them – for automations
also to delete them.

**Project access.** Per role you set whether its rights on projects and
packing lists apply to **all projects** or **only to assigned ones** –
also **"assigned projects only, overview without planning"**:
then the role opens only overview, packing list and chat in its projects,
never planning, schedule, access, history, open items or shortages –
whatever a membership says. The hint below the field explains it. What that
means and how someone gets assigned is in section 12, "Who sees which
project". Service cases someone is responsible for or takes part in they
work on regardless (section 7, "Working on the case").

**Special rights** are handed out independently of this:

| Special right | For |
|---|---|
| "See prices and calculation" | price columns, totals, price overview, changing prices, applying old prices; seeing and creating offers, order confirmations, invoices and cancellation invoices, handing invoices over to Lexware Office; with access to the settings, the Accounting page; customers' default discount and the highest discount of job functions and products; surcharges in the price of crew lines and services; the monthly statement of the service cases; rates, billing and discounts of vehicles and their bookings and what a trip is charged; revenue and totals in the project list; with the module Reports and read access to every project, the reports; the state of a project's invoice and the reminders of it; importing prices and discounts; reading the messages of the correspondence with a lock and – with "Write and send correspondence" – putting the lock on and taking it off |
| "See purchase prices" | purchase prices of material, buying-in prices of subrentals, internal costs of the vehicles and what vehicles from suppliers cost, profit from the project (with the two other rights as well), material and logistics costs in the project list; the share of the purchase price in the "Earnings" box of an item and of a model and the "Material" tab of the reports; the values of confidential custom fields |
| "Reopen closed projects" | |
| "Change article numbers that are in use" | |
| "Edit rental scales" | |
| "See hourly rates and personnel costs" | hourly and day rates of people, job functions (guide values), lines and times; assigning and removing job functions with rates of their own; surcharges in the costs of crew lines; personnel costs, approved expenses and profit from the project, also in the price overview per phase and in the project list; importing rates |
| "Approve times and record them for others" | the tabs "Approve" and "Expenses", seeing and recording other people's times and expenses, marking expenses as reimbursed |
| "Plan people in job functions they are not assigned to" | exception to the rule that someone is only planned in their own job functions; the other people appear marked in the selection |
| "See availability of material" | the traffic lights in the planning and the line dialog and the notes about missing material, the "Availability" box on a product's page, the timelines of products, models and items, the material utilisation, the shortages – page, start page, open items, notifications –, the calendar links of products, models and items (together with reading all projects; section 4, "Calendar link") and the same via the interface. Not: the stock of a product and the fleet |
| "Read correspondence" | the mails of the projects one may read (section 14) – those with a lock only together with "See prices and calculation" |
| "Write and send correspondence" | writing and answering mails from the project, sending documents; with the right to delete projects, also removing mails |

That way the warehouse can look after material and pack without seeing what
a project costs.

**Documents** (section 11) are created by whoever may edit the project; for
offers, order confirmations and invoices "See prices and calculation" is
needed as well. Delivery notes and crew dispositions can be seen by everyone
who may read the planning of the project – the warehouse too.

**Roles supplied** – suggestions you can change and add to (on an
installation in German with their German names, given in brackets):

| Role | Meant for | In short |
|---|---|---|
| Administrator | users, rights, master data, settings | everything |
| Project management (Projektleitung) | creating, scheduling and costing projects | projects "create and edit" (not delete); editing customers; **reading products**; reading material; prices and purchase prices |
| Warehouse (Lager) | looking after material, packing, issuing, taking back | material "create and edit" (not delete); packing; reading projects and products; purchase prices, but **no** rental prices; reading correspondence |
| Read only (Nur-Lesen) | accounting, management | reading everything, with prices; changing nothing |
| Personnel planning (Personaldisposition) | personnel planning | personnel and time tracking in full; reading projects and planning personnel in them; hourly and day rates; approving times |
| Crew | own deployments, working through the packing list, own times; every new person gets Crew or Freelancer | reading projects, packing "create and edit" – **assigned projects only, overview without planning**; recording times; no adding material; no prices; no availability of material; reading correspondence |
| Freelancer (Freie Kraft) | "Only the essentials: own deployments and time recording, no project info" | reading projects and packing lists – **assigned projects only, overview without planning**; recording times; no prices, **no availability of material**, no special rights |

**Start rights of the roles.** Four roles start with these
rights (table above): **Freelancer** – the description "Nur das Wichtigste:
Eigene Einsätze und die Stundenerfassung, keine Projektinfos", without the
special right "See availability of material" and with the project access
"assigned projects only, overview without planning" (a
membership cannot open the planning of a project for them);
**Crew** – plus "read correspondence"; **Warehouse** – material "create and
edit" instead of "delete", plus "read correspondence"; **Project
management** – projects "create and edit" instead of "delete", products
"read" instead of "edit".

**What the update did to the roles.** The role **Crew** got the
project access "assigned projects only, overview without planning" – but
only if it still had its start rights (assigned projects only, reading
projects, no special right). **All other roles** – also a Crew you had
changed; it keeps its project access – got the new special right "See
availability of material", so that nothing changes for their users. Each
change is in the change log. Freelancer has the
special right; its project access stayed as it was.

**Packing without adding material.** The crew packs in its
projects (section 10, "Packing with the Crew role"). Only someone who may
edit the project or may pack for **all projects** may **add material**
while packing – Warehouse and Project management still can, a role that
packs in assigned projects only and lacks "Projects: create and edit"
cannot. If such roles of your own need to add material, give them "Projects: create and edit"
or packing for all projects.

**Read only and accounting.** "Reading everything" means for Read only: all
modules except the settings. Read only sees the menu entry Accounting with
the outgoing documents (prices and reading every project). The page **Settings → Accounting**
(below), however, needs read access to the settings. If accounting
should fetch DATEV files there and see what went to Lexware Office, give the
role Read only the level "read" under "Settings" – or create a role of
your own, "Accounting": Settings "read" and the special
right "See prices and calculation", plus Projects "read". Read access to the
settings also shows logs and users; weigh up what you prefer.

**Requiring two-factor login.** On every role you can tick that its users
must set up two-factor login (section 2, "My account"). Whoever does not
have it yet goes straight to setting it up after logging in and cannot do
anything else first. For everyone who may change the settings, a
setting requires it (below, "Company data and settings").

**Resetting two-factor login.** If someone has lost both their phone and
their recovery codes: Settings → Users → the user → "Reset two-factor
login". They then log in with their password and set it up again. If the
only administrator is affected, `sudo rentalars reset_two_factor NAME` on the
server helps.

### Directory (LDAP)

If your company keeps its accounts in a directory –
**OpenLDAP** or **Active Directory** –, your colleagues can log in to
Rentalars with the name and password they use everywhere else, and the
**groups** they are in there decide which **roles** they get. You find it
under Settings → Users and rights → **"Directory (LDAP)"**; whoever may
read the Administration module sees the page, whoever may change it
changes it. It is **off by default**: as long as nothing is switched on,
only accounts with a password of Rentalars log in, as before.

**Before you start.** Have at hand the address of the server, the search
base for users and groups, and the name and password of an account that
may look people up in the directory (the "search account"). Then:

1. **Connection.** Click "OpenLDAP" or "Active Directory" under "Fill in
   suggestions:" to get usual values, then enter **"servers"** (one
   address per line, e.g. `ldaps://dc1.example.com`; several servers are
   tried one after the other). Enter the servers by their **name**, not by
   an IP address: the certificate is checked against the name. Use `ldaps://` or tick **"encrypt with
   StartTLS"** for `ldap://`: without encryption the password of every
   colleague goes over the network in the clear – the page, the connection
   test and the interface warn about an `ldap://` address without StartTLS. **"check the
   certificate of the server"** is on – switch it off for a test only;
   for your own certificate authority give the **"file with the CA
   certificate"** (the absolute path of a file on the server that Rentalars
   can read and that holds a certificate in PEM format – the page refuses
   anything else) or paste it under **"CA
   certificate (pasted)"**. **"timeout in seconds"** is 8 at first.
   Directory servers are usually in the company network; Rentalars
   connects to internal addresses only if the operator has allowed them in
   the configuration file (section \[network\], `allow_internal`).
2. **Search account.** **"search account (DN)"** and **"password of the
   search account"**. The password is stored encrypted and never shown
   again; leave the field empty to keep it, or tick "Remove the stored
   password". If you add another server or change the search account
   without entering the password again, the stored password is deleted –
   so that a password given for one server never goes to another. Without
   a search account Rentalars searches anonymously. If the secret key of
   the installation was changed, the page says so: enter the password
   again.
3. **Finding users.** **"search base for users"**, **"filter for users"**
   (`{username}` stands for what was typed; Active Directory
   `(&(objectClass=person)(sAMAccountName={username}))`, OpenLDAP
   `(&(objectClass=inetOrgPerson)(uid={username}))`) and the attributes for
   username, e-mail address, first name and last name.
4. **Finding groups.** **"find the groups"**: either **"Attribute of the
   user (memberOf)"** – Active Directory, and OpenLDAP with the memberOf
   overlay – with the "attribute with the groups", or **"Search in the
   groups"** with "search base for groups" and "filter for groups"
   (`{user_dn}` or `{username}`, e.g. for posixGroup). With the usual
   settings only the groups a person is directly a member of are read. For
   Active Directory groups inside groups the group search with the
   filter `(&(objectClass=group)(member:1.2.840.113556.1.4.1941:={user_dn}))`
   (with the outer brackets; without them Rentalars refuses the filter) is the
   way to try – checked against the filter parser, **not tried with a real
   Active Directory**. OpenLDAP has no such rule: there the groups that are to
   give a role must list the person as a direct member.
5. **At the login.** **"allow login with a local password"** (on): accounts
   with a password of Rentalars can still log in with it; off: only local
   accounts can, everybody else logs in with the directory. **"create
   accounts at the first login"** (on): someone from the directory who has
   no account yet gets one at the first login, but only if one of their
   groups has a role. **"link existing accounts by name"** (**off**): see
   "Existing accounts" below. **"compare the accounts every night"** (off): see
   below.
6. **Groups and roles.** Under "Groups and roles", **"New assignment"**
   links a **"Group"** (its DN, at most 480 characters; or only its name,
   e.g. `admins`) to one or several **"Roles"**. **Use the full DN**: a bare
   name matches a group of that name *anywhere* in the directory, also in a
   part that others can write to; the page and the interface warn about such
   an assignment (`name_only`, `warning`). Existing assignments by name keep
   working. A user gets the roles of **all** groups they are
   in. **"Priority"** and **"last match"** are for exceptions: the lowest
   number is applied first, and a user who is in a group with "last match"
   gets no assignment with a higher number. Deleting an assignment takes
   the roles it gave back at the next login. Roles from the directory
   cannot be taken away by hand in the user list; roles an administrator
   gave stay. **Without any assignment nobody can log in with the
   directory** – the page says so in red.
7. Tick **"log in with the directory"** at the top and save. The page
   only accepts the switch with a server address, a search base for
   users and the attribute for the username (and, depending on the way
   groups are found, a search base for groups or the attribute with the
   groups). It also refuses to switch **"allow login with a local
   password"** off as long as no active local (emergency) account with a
   password and the right to change the settings exists (below).

**Testing, without risk.** Under "Test" – the tests use the saved settings
and write nothing:

- **"Test connection"** goes through the steps one by one and shows
  "OK" or "Problem" with the detail of each ("Result of the connection
  test").
- **"Test login"** asks for a user name and, optionally, the password. It
  shows the entry in the directory, the attributes, the groups, the
  assignments that apply, the roles, whether the password is accepted and
  – "Login would" – what the login would do: create a new account, take
  over the existing account of the same name, use it, activate it again,
  or be refused (and deactivate the account), with the reason. The test is
  entered in the security log as "directory login tried by an administrator" and
  **counts towards the lockout after failed attempts** like a login (through the
  interface: answer 429), so that it is no way to guess passwords. If the account
  is linked to another entry because the user was **moved** in the directory, the
  test shows "Moved in the directory?" and the button **"Adopt the new entry"**
  (with a confirmation; through the interface `POST /ldap/adopt-dn`): it links the
  account to the entry the directory finds for the name – **only if the old
  entry no longer exists**, and never for a local account or one with "has all
  rights". It is noted in the history of the account and in the security log.
- **"Show the differences"** compares all accounts that the directory keeps
  with it and lists what would happen to them (deactivate, activate again,
  bring up to date, link to the directory) with the roles before and after;
  **"Apply these changes"** does it. Nobody is created here. If more than
  half of the accounts, and more than three, would be deactivated, nothing
  is done – that looks like a wrong filter or a directory that does not
  answer. The server command `sudo rentalars ldap_sync` shows the same;
  `--apply` writes, and `--force` overrides the stop.

**What the login does.**

- Rentalars first asks its own accounts. Only if the password does not fit
  there does it ask the directory. The protection against guessing, the
  security log and the two-factor login stay as they were: after the
  directory has accepted the password, a user with two-factor login is
  asked for the code.
- **First login:** the account is created with name, e-mail address and
  roles from the directory, without a password of Rentalars. An existing
  account of the same name is taken over, once – **only if "link existing
  accounts by name" is on** (off by default; see "Existing accounts"). An e-mail
  address that another account uses already is not taken over. Two names that
  the database cannot tell apart (`müller` and `muller`) are refused as well, and
  an account that is linked to an entry is not re-linked by name to another one.
- **Every login:** first name, last name, e-mail address and roles are
  brought up to date. Someone who is in none of the groups with a role
  cannot log in, and their account is deactivated; if they come back to a
  group, the account is activated again – but only if the directory, and
  not an administrator, had deactivated it.
- **User names** must consist of letters, digits and `@ . + - _` and be
  at most 150 characters long; an entry whose name does not is **refused,
  not shortened**, with that reason in "Test login". (Typed names of more
  than 256 characters or with control characters are not even sent to the
  directory.) First and last names longer than 150 characters are cut.
- **Passwords** are changed in the directory. In Rentalars the account
  page and "My account" say so, and the buttons "Send link for setting a
  password" and "Set one-time password" are missing in the user's form.
  "Forgot your password?" does not apply.
- The user's form (Settings → Users) shows the box "Directory (LDAP)": the
  entry in the directory, "Last confirmed by the directory" and, if the
  directory deactivated the account, "Deactivated by the directory".

**Existing accounts.** Someone who has an account in Rentalars already logs in
through the directory **only if the account is linked** to it. Linking by name
is **off** ("link existing accounts by name"): a name in the directory does
not prove that it is the same person, and a linked account would keep the
roles an administrator gave it. With the switch off the login is refused; the
user sees only a general refusal, the security log has the reason, and "Test
login" says "not linked to the directory". The page warns in red while the
switch is on. To bring existing accounts into the directory, an administrator
switches it on, lets the people log in once, and switches it off again; linked
accounts keep logging in. Accounts that use a password of their own in
Rentalars are not affected as long as login with a local password is allowed.

**Do not lock yourself out.** Mark the account of at least one
administrator as **"local (emergency) account"** in the user's form. It
logs in with its own password only, even if the directory is on, and the
directory never changes its roles or deactivates it. The same holds for an
account with "has all rights": both are protected also against a directory entry
of the same name or with the same DN, they are not part of the comparison, and
their link to the directory is cleared as soon as an account becomes local or
gets all rights. The page warns in a note if no local account
can change the settings. The directory is never asked for these accounts.
If the directory does not answer, the login page says "The company
directory could not be reached just now" besides "Name or password are
wrong." and the security log has the entry "directory not reachable".

**Security log.** Besides the normal login entries, the security log
(section 16, "Security log") has the kinds "directory login
refused", "directory not reachable", "account created or changed by the
directory", "roles changed by the directory", "accounts compared with
the directory" and "directory login tried by an administrator".

**Switching the directory off again.** Accounts that existed only in the
directory and have no password in Rentalars are not stranded: an administrator
can invite them or set a password for them.

**Interface.** Everything on this page can be done through the interface
too (section 16, "API tokens – Rentalars for other programs"); the users
there show whether an account is local, its entry in the directory and the
roles from the directory.

*Limits:* Rentalars was tested against the usual filters and attributes of
OpenLDAP and Active Directory, **not against a real directory of yours** –
use "Test login" first, with a user from each group. Groups inside groups are
not followed by the usual settings (see step 4). A user is found by the filter and the name typed at the
login; Rentalars does not copy the directory, only the people who log in
(and, with the nightly comparison, keeps those up to date).

### Company data and settings

**Settings → Company data and settings** – two forms on one page:

- **"Company data":** name, address, phone, e-mail, website, tax number, VAT
  identification number, bank with IBAN and BIC, **logo** (PNG or JPEG).
  They appear on the packing list and on the documents – in the header the logo
  with the address, in the footer the address, contact, tax numbers and bank
  details. In addition:
  - **"register and management"** – appears in the footer of the
    documents, e.g. "Amtsgericht Musterstadt HRB 1234 · Geschäftsführung:
    …";
  - **"payment terms in days"** – for invoices, unless the customer has
    terms of their own; 14 by default;
  - **"address of the warehouse"** – on one line, such as "Industriestraße
    5, 12345 Musterstadt": the trips of the projects begin and end here
    (section 7, "The trips of a project"). The "Route in Google
    Maps" links always start at your current location, not at the warehouse
    (section 6, "Route and map"). If it is empty, the company's address
    applies. Below the form are "Route in Google Maps" to the company,
    "Route to the warehouse" and "Show map".

  For the XRechnung, **e-mail address**, **phone number** and **VAT ID or
  tax number** are required (section 11). Fill in everything before the
  first invoice is made. The company name also appears in the sender of
  mails that are sent, in the signature (`{firma}`, section 14), at the end
  of every mail Rentalars sends by itself (section 14, "Signature"), and in
  small print in the sidebar below "Rentalars" (section 2).
- **Language of documents**: Deutsch or English – the
  language in which offers, order confirmations, delivery notes, invoices,
  packing lists and crew dispositions are made, and the mails Rentalars writes
  to customers by itself, such as the answers of automations. Fixed texts
  such as column names, units and dates follow it; what you typed
  yourselves – document templates, text blocks, mail templates, product
  names – stays as it is (section 11, "Language"). It applies to the whole
  company; each person chooses the interface for themselves (section 2, "My
  account"). The default is the language of the installation.
- **Buffer times** before and after use (section 9).
- **"usual start time"** and **"usual end time":** the times of day a new
  project is filled in with – 12:00 and 12:00 by default. If the end time is
  not after the start time, the project ends on the following day (12 to 12:
  one day, section 7).
- **Passwords and login:** "minimum password length", "failed logins before
  lockout", "lockout duration (minutes)".
- **"people may see their own hourly rates":** switched on – this also
  applies to the day rates. If you do not want that, untick it; then only
  users with the special right for personnel costs see rates and amounts.
- **"ask again when the times change":** switched on (the default), a
  person who was requested or has accepted automatically gets a new
  deployment request when the start or end of their crew line changes, and
  the line is back at "requested" until they answer; declined lines do not
  (section 12, "Requests: acceptance or refusal"). Switched off, you ask again
  yourself with "ask again".
- **"answer to deployment requests"**: how people answer a deployment request – "by
  the link in the browser", "by reply mail" or "both" (the default). Below,
  it says which mailbox answers by mail go to – or that there is none yet
  (section 12, "Answering deployment requests by mail").
- **"log out after … minutes without activity":** 240 by default.
- **"two-factor login required for administrators":** for everyone who may
  change the settings, and every account with all rights. Switch it
  on at the latest when Rentalars can be reached from the internet.
- **"prefix of the project tag in mails":** "RL", the tag then reads
  `[RL#2026-0042]` (section 14).
- **"largest file to upload (MB)":** 50 MB by default, at most 500 MB – for
  project files and show files, hall plans, receipts for expenses and
  attachments of mails that are sent. For show files with media it may be
  more (section 11, "Files of the project").
- **"load maps at once":** off (the default), a map only appears after a
  click on "Show map" – only then does the address go to OpenStreetMap; on,
  every page with an address shows its map at once (section 6, "Route and
  map").
- **Bookkeeping and accounting** (own box): **"use Rentalars as
  accounting software"** – on (the default). Off: no invoices and cancellation
  invoices, handing over to Lexware Office and DATEV export and all tabs of
  bookkeeping (incoming documents, open invoices, bank, EÜR, archive, asset
  register …) are hidden; invoices created earlier stay readable (section 11,
  "Invoices in another program").
- **Hints at unusual times:** **"show hints at working times"** (switched on) switches all hints on or off for everyone; the limits
  below it stay stored. "hint: working day longer than … hours" (10), "hint:
  a break is due after more than … hours of work" (6) with "hint: that break
  lasts at least … minutes" (30), the longer break from 9 hours with 45
  minutes, "hint: rest between two working days shorter than … hours" (11);
  0 switches a single hint off (section 13, "Hints at unusual times").
- **"travel costs per kilometre":** €0.30 by default – for trips with your
  own car recorded as expenses. A trip keeps the rate it was recorded with
  (section 13, "Expenses and travel costs").
- **"deduct the way to work from trips"** (switched on): for
  trips by kilometre, twice the person's "Distance home – company" is
  deducted once a day per project (section 13, "Expenses and travel costs").
  Switched off, nothing is deducted.
- **"API calls per token and minute":** 600 by default (below, "API
  tokens"). 0 means: no limit.
- **Retention periods** for logs (the access log too), notifications and
  background tasks (below, "Retention periods").

The **mailboxes** and the **signature** are not here but under
Settings → E-mail → "Mailboxes and signature" (section 14).

**Route service**. Below the forms, the box **"Route
service"** shows whether it is "set up" or "not set up", and if so its
kind, the region and how old the map is. The route service suggests the
planned kilometres of a vehicle on a trip from the route, always
changeable (section 7, "Logistics"); the route is reckoned by your server
or by a routing server of the operator's or in Germany, and Rentalars
locates the places as on the maps. Only whoever runs the server can set it
up, update or remove it, with the commands the box names (guide
"Operation", "Route service"). Without a route service the kilometres are
typed in by hand.

### Number ranges

For projects, customers, material IDs and the documents: prefix, minimum
number of digits, next number, and whether to restart every year. In the
prefix, `{year}` stands for the current year – with the default prefix
`{year}-` you get project numbers like `2026-0001`. At the top of each range
you see what the next number will look like.

**Project numbers without "P-".** `{year}-` is the default prefix of the
projects. The number with
"P-" stays on the project as its earlier number (section 7, "Creating a
project"). If you change the prefix, this only applies to new
projects; existing ones keep their number. Rentalars never hands out again a
number that a project once had.

The documents (section 11) have ranges of their own: **"Offers"**
(`AN-{year}-`, so `AN-2026-0001`), **"Order confirmations"** (`AB-{year}-`),
**"Delivery notes"** (`LS-{year}-`), **"Invoices and cancellations"**
(`RE-{year}-`) and **"Crew dispositions"** (`CD-{year}-`) – all restarting
every year.

You can raise the "next number", for example to carry on from an existing
numbering. Only lower it if the numbers really are still free – never for
invoices: invoice numbers must be continuous and unique.

### Surcharges

**Settings → Surcharges** ("Surcharges for night, Sunday and
holidays") sets whether and by how much crew lines cost more at certain
times – separately for the customer's price and for the personnel costs.
How Rentalars calculates with this is in section 12, "Surcharges for night,
Sunday and holidays". The surcharges are a **list of rules** that
works in any country.

Surcharges for night, Sunday and holidays go **only to crew lines** billed
by the hour (by plan or by effort) – never to material, incidental costs,
surcharges or any other line, and not to a crew line with a flat rate or a
day rate. Only services have the switch to exclude them.

- **"Which crew lines":** **"Surcharges on the price of crew lines"** and
  **"Surcharges on the personnel costs of crew lines"** – both off at first. Switched on,
  crew lines by the hour that are planned **from then on** get the
  surcharges; lines planned before stay as they are. Every line keeps its
  own switches in its dialog, and a service can exclude its lines on its
  product page; other products have no such switch – their lines never get
  these surcharges.
- **"Rules":** each rule has a card of its own. In the first row: **"Name"**
  (it appears in the planning and on documents), **"applies"** – when it
  applies –, **"on the price, in percent"**, **"on the costs, in percent"**
  (0 means no surcharge), **↑** and **↓** for the order, and **"Delete"**.
  Below, the details that fit the chosen kind:
  - **"at a time of day"** – from … to, also over midnight (night 20:00 to
    06:00); with the tick **"only for work begun before midnight"** the rule
    only applies then and takes the place of the other time-of-day rules
    (the 40 % from midnight to 04:00 according to § 3b EStG);
  - **"on weekdays"** – Mon to Sun to tick, if you wish from a time of day
    (Saturday from 13:00);
  - **"on public holidays"** – on the statutory ones and your own (below),
    if you wish from a time of day;
  - **"on a day of the year"** – day and month, if you wish from a time of
    day (24 December from 14:00).

  **"Add a rule"** brings a new card; to remove one, tick "Delete" and save.
  Without JavaScript there is always an empty card for a new rule at the
  bottom.
- **How the rules combine:** of the rules on weekdays, holidays and days of
  the year only the highest rate counts, likewise of the time-of-day rules;
  the two are added – night 25 % plus holiday 125 %. If the rates are equal,
  the rule further down counts. Price and costs each choose their rule for
  themselves. Rules with the same name and the same rate appear as one line
  in the planning and on documents.
- **Until when a day with a surcharge reaches into the next:** for work
  begun before midnight, the day rules of the previous day (Sunday, holiday)
  still apply until this time – according to § 3b EStG until 04:00. Empty
  means: never.
- **"Set as § 3b EStG"** replaces all rules, after a confirmation, with the
  tax-free rates according to § 3b EStG and sets 04:00; holidays, federal
  state and the two switches at the top stay. The rules are then:

  | Rule | Applies | Rate |
  |---|---|---|
  | Night | at a time of day, 20:00 to 06:00 | 25 % |
  | Night 0–4 | at a time of day, midnight to 04:00, only for work begun before midnight | 40 % |
  | Sunday | on weekdays: Sun | 50 % |
  | Holiday | on public holidays; and on 31 December from 14:00 | 125 % |
  | Christmas and 1 May | on 24 December from 14:00, on 25 and 26 December, on 1 May | 150 % |

  Whether the rates suit your payroll is something to settle with whoever
  does your payroll accounting; every value can be changed. A new
  installation has these rules from the start; if you delete them all, the
  empty list means: no surcharges.
- **"Holidays":** **"public holidays of"** – the federal state whose
  statutory holidays apply, the same for all projects; without a choice
  only the nationwide ones. For Bavaria, Saxony and Thuringia there are the
  variants with and without Assumption Day or Corpus Christi, plus the city
  of Augsburg with its Peace Festival. If you untick **"statutory holidays
  of Germany"** (ticked by default), only your own holidays count – for
  example when you work in another country; the list below then says "only
  own holidays".
- **"Own holidays"** – for work in another country or days the company
  observes; they apply to the whole company like the federal state. "Add a
  holiday", then the name and one of three kinds: **"every year on"** (day
  and month), **"once on"** (a date) or **"days from Easter Sunday"** – a
  number from −80 to 240, such as Easter Monday 1, Ascension Day 39, Whit
  Monday 50, Corpus Christi 60.

"Save settings". Below are the **holidays** of this year and the next, as
Rentalars calculates them – the statutory ones of the chosen federal state
and your own. Check them once. A change applies at once to every line with
surcharges, also in finished projects; documents already created stay as
they are.

The rates can only be seen and changed by whoever has the matching right:
the rates on the price with "See prices and calculation", those on the
costs with "See hourly rates and personnel costs" – in the change log too.

**Where do the holidays come from?** Rentalars calculates them itself, per
federal state – including the movable ones that depend on the date of
Easter, such as Good Friday, Easter Monday, Ascension Day, Whit Monday and
Corpus Christi. No service on the internet is asked for this; it needs no
connection to the outside and no subscription. The list at the bottom of
the page shows the result.

### Automations

**Settings → Automations** lets Rentalars do something by itself when
something happens: answer every new inquiry with a confirmation of receipt,
notify the project manager when a project is confirmed, note an open item
"Ersatz suchen" (find a replacement) when someone declines, make a service
case of a reported defect. Every rule reads "If … then …"; **"New
automation"** creates one:

- **Name** – shown in the list and with every run – and **active**.
- **"If …"** – the trigger:
  - **"a mail without project tag arrives"** – in a mailbox that takes in
    mails without project tag, or at a further address that takes them in
    as an inquiry or straight away as a service case (section 14, "Setting
    up mailboxes"); under "only in the mailbox" one of them, empty for
    every one. If the mail became a service case straight away, the run
    belongs to that case – so an open item lands there;
  - **"a project reaches a status"** – you choose the status; this also
    counts when creating and when Rentalars sets the status itself, such as
    "Out" after issuing;
  - **"an answer to a deployment request arrives"** – acceptance, refusal or
    both, whether in the browser, by reply mail or through the interface;
  - **"a follow-up is due"** (section 7, "Follow-up");
  - **"the follow-up of a service case is due"** – with
    "Status of the service case", if you like, only in one status, such as
    "Waiting to close";
  - **"new communication in a service case"** – a mail
    received or sent, a mail moved into the case by hand or a new chat
    message; if you like, only one of these kinds and only in one status.
    Out-of-office replies, delivery failures, edited chat messages and
    notes in the correspondence (section 14) do not count;
  - **"a defect is reported"** – on an item's page, on return
    or through the interface (section 4, "Report defect").
- **"… then"** – the action, one per rule; for several actions you create
  several rules:
  - **"answer the mail"** – only with the trigger "mail without project
    tag": "Subject of the answer" (empty: "AW:" and the subject) and "Text of
    the answer". A confirmation of receipt is suggested ("Hello {name},
    thank you for your mail …") – it goes to customers and is therefore
    phrased formally;
  - **"notify a person"** – "whom": a chosen user, the project manager, who
    asked for the deployment, or whom the follow-up is for, depending on the
    trigger; with "Title of the notification" and "Text of the
    notification";
  - **"note an open item in the project"** – only with triggers about a
    project;
  - **"set the status of the service case"** – only with the
    triggers of a service case: "New status" Open, In progress or Done.
    The statuses with a follow-up are set only by a person;
  - **"create a service case"** – only with the trigger "a
    defect is reported": with **"Title of the service case"** (empty:
    "Defect", the ID and the short name, such as "Defect 0042 SM58"),
    **"Description of the service case"** (empty: what is defective, the
    item, where it was found, who reported it and when) and
    **"Responsible"** – that person is told by a notification that the case
    is theirs; empty, nobody is responsible yet;
  - **"put it under Projects → Inquiries"** – also only for a
    defect report: it waits there with the **"Subject in the list of
    inquiries"** until someone makes a service case of it or takes it off
    the list (section 14, "Inquiries"). For a defect report the third
    action is "notify a person", to a chosen user.

In the texts, **placeholders** fill in what has just happened; which ones
exist is shown in the form under "Placeholders for the texts", depending on
the trigger: `{name}`, `{sender}`, `{subject}` and `{mailbox}` for a mail;
`{project}`, `{project_number}`, `{project_name}`, `{status}`,
`{project_manager}` and `{link}` for a project – for a service case,
`{status}` and `{link}` are those of the case; in addition `{person}`,
`{answer}`, `{job_function}`, `{deployment}` and `{note}` for an answer to
a deployment request, `{follow_up}`, `{follow_up_note}` and `{for}` for a
follow-up, `{communication}` (the mail or chat message in a few words,
such as "Mail from customer@example.org: Microphone broken"; for a mail
with a lock without the subject: "Mail from … (with lock)" or
"Mail sent (with lock)" – so also in the title of a notification without
a title of its own) for
new communication; `{id}`, `{short_name}`, `{model}`, `{product}`,
`{serial_number}`, `{description}` (what is defective), `{found}` (where,
such as on the return of a project), `{reported_by}`, `{reported_at}` and
`{link}` (the address of the item) for a defect report; `{company}` and
`{date}` always. Every placeholder has an English and a German
name – `{firma}`, `{datum}`, `{absender}`, `{projektnummer}`,
`{wiedervorlage}`, `{kommunikation}`, for a defect report `{kurzname}`,
`{modell}`, `{produkt}`, `{seriennummer}`, `{beschreibung}`, `{gefunden}`,
`{gemeldet_von}`, `{gemeldet_am}` and so on; both names work in every
text, and the form shows the names of your language. A placeholder
Rentalars does not know stays as it was written.

**Protection against reply loops.** An out-of-office reply that answers a
confirmation of receipt, which is confirmed again … – Rentalars prevents
this. It **never** answers:

- mails marked as sent automatically – out-of-office replies, delivery
  failures, mailing lists, newsletters;
- mail systems and no-reply addresses (mailer-daemon, postmaster, no-reply
  and the like) and its own addresses – the mailboxes, the sender of the
  system mails, the company's address;
- a sender the same automation has already answered today – everyone gets
  at most one answer per rule and day.

The answer goes through the mailbox in which the mail arrived (otherwise
the one that sends the correspondence), with the address the
mail was written to as the sender – for a mail to `support@`, that is, from
`support@` –, to the reply address of the mail; it is marked as an
automatic reply so that other systems do not answer back, ends with the
note about Rentalars (section 14, "Signature") and appears in the mail log
as "automatic reply". The mail itself stays as an inquiry until someone
takes it over – unless it became a service case straight away.

With a follow-up that has a time of day, **"a follow-up is
due"** only triggers from that time on; the placeholder `{follow_up}`
then reads something like "Mon 20/10/2026 at 14:30".

**Automations for service cases.** Three automations are set
up and switched on – in a new installation as in an updated one:

| Automation | If … | then … |
|---|---|---|
| Waiting to close: close at the time set | the follow-up of a service case is due, status "Waiting to close" | status "Done"; the follow-up is removed |
| Waiting to close: open again on new communication | new communication in a service case, status "Waiting to close" | status "Open"; the follow-up stays as a reminder |
| Backlog: open again when the follow-up is due | the follow-up of a service case is due, status "Backlog" | status "Open" |

An installation that was already running in German has them under their
German names ("Wartet auf Schließen: zum Termin schließen" and so on). You
can change, switch off or delete them. As long as the first one is
switched on, nobody gets a follow-up notification at the time set for
"Waiting to close"; if you switch it off, the notification comes as usual.
The automations of a service case also run if nobody is responsible for
it. What an automation does itself – setting a status, say – does not
trigger another automation. Just before it runs, Rentalars checks again
that status and time are still the same; if someone has changed the case
in the meantime, the run appears as "left out" with the reason. If a new
mail should also reopen a waiting case, create a rule like the second one
with the status "Waiting".

**Defect report → service case.** Every installation has one more
automation, switched on: when a defect is reported, it creates a service
case. The case is internal – your own material, no customer –; for
customer material it belongs to its owner; the photo of the report goes
into its files (section 7, "Service cases"). An installation running in
German has it under the name "Defektmeldung → Servicefall". You set title,
description and "Responsible" on the rule. You can change it, switch it
off or change it to "put it under Projects → Inquiries" if someone should
decide first. One report makes at most one service case.

**The automations that come with Rentalars**. The four
automations Rentalars brings – the three for service cases and "Defect
report → service case" – are rules like your own: you edit them, switch
them off and on and delete them with the same rights, in the browser and
through the interface, and every change is in the change log. In the list
they carry **"default"**, and **"changed"** as soon as they differ from how
they came – switching off does not count, nor does the name in German or
English. At the top of the form of such a rule it says "This automation
came with Rentalars." or "… and was changed since." If one is missing, the
list has **"Restore default automations"** at the top: after a question
that names what will be created, Rentalars creates the missing ones as
they came, switched on; those that are there – changed or not – stay as
they are. A rule of yours with the same name does not count as one that
came with Rentalars. No update creates a deleted one again or overwrites a
changed one.

**The list** shows under **"Rules"** every automation with "If" and "Then",
how often it ran and how often something failed; next to it **"Edit"**,
"Switch off" or "Switch on" and "Delete" – in one row and of
one height, on the phone too. Via "Columns" you show the column
**"Origin"** ("default" or "default, changed"). In the form of a rule
"Delete" stands next to "Save automation". Under **"Runs"** every run is listed with time,
automation, event and result – "done", "left out" with the reason (such as
"got an answer of this automation today already") or "failed" –, which you
can filter by automation and result. Runs are kept for a year, even if their
rule has been deleted. A run interrupted by a restart is not repeated, so
that nothing goes out twice. If a mailbox is deleted, the rules that applied
only to it switch themselves off.

### Notifications of the company

Under **Settings → Notifications** you set for the whole
company when Rentalars reports shortages, when it reminds
you of invoices still to be written, and when it reminds of
times to approve. Whether a person gets them in
Rentalars, by e-mail or in the app, each person still chooses under My
account → Notifications (section 15, "Notifications"). Whoever may read
the settings may view the page; whoever may edit them may change it.

In the box **"Shortages"**:

- **How often**: every day, on working days (Monday to Friday, except
  holidays – the holidays under Settings → Surcharges count), once a week
  on the **day of the week** you choose, or never.
- **Time of day**: Rentalars checks within a minute of this time.
- **How far ahead (weeks)**: shortages of projects that begin within this
  many weeks – 1 to 26.
- **Report known shortages again at every check**: off, Rentalars reports
  each shortage once – again only if it grows, or if it was resolved and
  comes back. On – the default –, every check also reminds of
  all open shortages already reported: in **one** message per project –
  for one shortage "Still a shortage in …: 3 × Top speaker missing", for
  several "Still shortages in …: 7 products" with the list in the text,
  one line per product ("2 × Top speaker missing"). New or grown shortages
  still come one by one ("Shortage in …"). If you do not want
  it, switch it off here.

The default is every day at 4:15, four weeks ahead, with the reminder of known shortages. Below the fields you see when the last
check was, how many shortages it reported and when the next check is. If
you change the time or the rhythm, it applies from the next date on; a
time already past today is not made up. If the server was off at the time
of a check, Rentalars makes it up once. The report goes to the project
manager and the members who may edit the project; if a project has none,
to everybody who may change projects. A shortage already reported stays
known even if its project now begins further ahead than the lead time –
so shortening the lead time or moving a project does not report it a
second time.

In the box **"Invoices"** (section 11, "Invoices still to be
written"):

- **"Remind of invoices"** – switched on (the default), Rentalars reminds
  you of every closed project without an invoice until the invoice is
  there, "Invoice issued" is ticked or the project is marked "No invoice
  needed".
- **"Time of day"** – once a day at this time; 9:00 by default.
- **"First reminder after (days)"** – days after the project was closed;
  1 by default, 0 means on the day it was closed.
- **"Then again every (days)"** – 7 by default.
- **"Also remind"** – a person reminded besides the project manager, and
  for projects without one; empty, only the project manager. Only users
  who may see prices can be chosen.
- **"Service cases too"** – also reminds you of done service cases with
  something to charge; on by default. Only cases done **after it was
  switched on** are reminded of – after an update, those done since;
  earlier ones still show as "Invoice open" in the lists, but without a
  reminder. Switching it off and on again moves that moment.

Below are the last and the next check with the number of projects
reminded of, and since when closed projects count;
Rentalars does not remind you of projects closed earlier.

In the box **"Times to approve"** (section 13, "Handing in
and approving"):

- **"Remind of times to approve"** – switched on (the default), Rentalars
  reminds everyone who may approve times of the submitted times and
  expenses waiting for them under Personnel → Approve – each only of those
  they may approve, not of their own.
- **"Time of day"** – 8:00 by default.
- **"First reminder after (days)"** – days after the day of handing in;
  1 by default, 0 means at the next check after handing in.
- **"Then again every (days)"** – as long as something waits; 1 by
  default, that is every day.

Below are the last check with the number of people reminded and the next
one. If the server was off at the time of the check, Rentalars catches up
once. Whether someone gets the reminder in Rentalars, by e-mail or not at
all, they choose themselves under My account → Notifications ("Times
waiting for my approval").

### AI

**Settings → AI** controls whether and with what Rentalars
uses language models – for the summary of the correspondence and for reply
drafts (section 14) and for reading invoices in "Enter a
purchase" (section 4). **Everything stays off until you switch it on.** The
short overview without AI is always there. Whoever may change the settings
may change this.

- **Local AI:** a small language model on your own server. Mails it
  summarises do not leave the server, and it costs nothing per use. Only
  whoever looks after the server can set it up – with a command via SSH
  that the page names (`sudo rentalars ai install`; guide ["Operation"](operations/operation.md),
  "AI"). Until then it says "not installed". Afterwards the page shows
  status, model and server; **"Measure the speed"** sends a test question
  and shows how fast the answer came. **"Switch summaries with local AI
  on"** switches the summaries on; the same button switches them off
  again.

  "Local AI" also shows the **processor** (physical and
  logical cores, whether AVX2 and FMA are there) and the **measured
  speed**: how fast the AI reads and writes, and how long a summary of
  some 20 mails takes with it. "Measure the speed" measures both again;
  every summary keeps the values up to date. If the AI is too slow,
  Rentalars recommends the smaller model Qwen3 1.7B and names the command
  for the server; only whoever looks after the server changes the model.
  Without AVX2 or FMA the AI runs many times slower – in a virtual machine
  set the processor type to "host" (Proxmox: Hardware → Processors → Type:
  host) and shut the machine down and start it again (section 18, "Why is
  the local AI so slow?"). After an update the server takes over the
  settings of the local AI by itself; nobody has to install it again.
- **Uses:** for **"Summary of the correspondence"**, **"Reply draft for
  mails"** and **"Reading invoices"** you choose "Off", "Local
  AI" or one of the interfaces below, then "Save uses". All are off at
  first. **"Reading invoices"**: in "Enter a purchase" the AI reads an
  uploaded invoice (PDF with text) and suggests supplier, number, date,
  totals and positions, with serial numbers and, for new
  models, category and product; Rentalars reads the amounts itself, as the
  invoice prints them. You check every row before anything is created.
  Off, Rentalars takes only the number, the date, a known supplier and the
  totals from the text (section 4, "Entering a purchase"). So that the AI
  can choose category and product, Rentalars names your categories and up
  to 40 products of your own (no customer material) to it. If
  the chosen interface is on the
  internet, a red note below says that the text of an uploaded invoice
  leaves the company when it is read – an invoice carries prices, your
  customer number and addresses; the names of your categories and of
  those products go along with it. **"Suggestions for templates"**
  – suggestions for project templates from earlier projects – are listed
  as "later".
- **Interfaces (OpenAI-compatible):** for a server that speaks OpenAI's
  interface – Ollama, LM Studio or vLLM in the company network, or a cloud
  service. **"New interface"**: name, base URL, model, API key (stored
  encrypted and never shown again), timeout and context size. The timeout says how long Rentalars waits when the server sends nothing
  – the answer itself may take longer. An interface
  is used only for the uses you assign to it. If the address is on the
  internet, Rentalars shows in red **"cloud – data leaves the company"**:
  whatever you send there – the mails of your projects, if
  chosen the text of your purchase invoices – goes to this
  service. Use it only if your contract with it allows the processing of
  these data; whether you need a data processing agreement is for you to
  check. An address on the internet must begin with
  `https://` – with `http://` Rentalars refuses to save it, because the
  mails and the key would travel unencrypted – and Rentalars follows no
  redirection to another address. An address in your own network only works if the server allows it
  (guide ["Operation"](operations/operation.md), "Connections into the internal network").
- **Log of the AI calls** ("All calls"): which use asked which model when,
  how long it took, how much text went there and back and whether it
  worked – **never the content**. It is kept for a year.

- **Automatic summaries**: the box "Automatic summaries"
  with its status ("on", "off", "stopped: other provider", "no
  provider") and the last run; **"Open"** leads to the page of its own,
  Settings → AI → **"Automatic summaries"**. It has three parts: **"Where
  the data go"** (provider, what is sent, what is taken out, what is never
  sent; the buttons **"Show what would be summarised"** – a trial that asks
  no model and stores nothing – and **"Run now"**, which starts a run
  outside the window if the summaries are on), the **"Settings"** and the
  **"Runs"**. The settings:
  "Make automatic summaries every night" with the tick "I have read what
  goes to the provider and agree"; "window from" and "window until" (1:00
  to 5:00; a window may cross midnight, equal times mean always); "most
  summaries per night" (20); "token budget per night" (200,000; 0 is no
  limit); "Projects in these statuses" (at first the open ones from
  inquiry to returned) and "Service cases in these statuses" (open, in
  progress, waiting, closing); "least time between two summaries in hours"
  (20); "least number of mails" (2); "earlier summaries kept" (5); under
  "What the job reads" the ticks "Read notes written into the correspondence"
  (on), "Read the chat of the project" (**off**) and "Read messages with
  lock" (**on** – in projects every message starts with the lock, so the
  job would otherwise read nothing); under "For all summaries" "Send the
  names of attached files", "Taken out of every text before it goes to the
  AI" (IBANs, card numbers, secrets, e-mail addresses, phone numbers, all
  ticked at first), "longest text per summary" (150,000 characters; if
  there is more, the oldest mails are left out) and "summaries by hand per
  user and hour" (30). The three last apply to summaries by hand as well.
  The background timer of the server starts the run by itself in the window, once a night.
  The page is for whoever may use the Administration module; changing
  needs write access. **Read section 14, "Automatic summaries at night",
  before you switch it on** – it says what leaves your company.

  Changing the provider of the summaries (Uses → "Summary of the
  correspondence") to another **server** stops the job until you confirm
  again; the consent is bound to the server (the local AI, or the scheme,
  host and port of the interface), not to the name.

**What it costs.** The local AI costs nothing but electricity and memory on
your server; an interface to a cloud service costs whatever its provider
charges per call. Automatic summaries cost one call per changed project and
night, within the number and token limits you set.

### Master data

- **Categories and codes.** A shared structure for material and products,
  as deep as you like ("Sound > Microphones > Radio mics"). Only **main
  categories** carry a **code**; it becomes the start of the article
  numbers. A code already used in article numbers can no longer be changed,
  and the category cannot be deleted – only deactivated. On the category you
  also set:
  - the **category-specific fields**: per field position, label ("Length"),
    type (text, number with unit, choice, yes/no), unit ("m") and, for
    "choice", the options, one per line. The field with the smallest
    position is **the** category-specific detail shown in the material
    list; all others appear in the form of the model and can be set
    differently on the item (section 4). Subcategories inherit the fields.
    Rentalars does not accept a number field "Power" (or "Leistung") in
    watts:
    every model has the power as a field of its own, "Power (W)".
  - **"Presets for new products"**: product kind, unit, tax rate, billing
    mode.
  - the category's **rental scale** and different **buffer times**.
  - **"Customer material"** – only on main categories with their own stock:
    their products belong to a customer, have an owner and no price, and can
    only be planned in projects of that customer (section 5, "Customer
    material"). Subcategories follow their main category. The tick can only
    be set or removed while the category has no products.
- **Rental scales:** see section 5. They are in the box "Projects and
  personnel".
- **Tax rates:** 19 % and tax-free are supplied.
- **Units:** supplied are Piece (rental), Piece (sale), Kit (rental), Kit
  (sale), Hour, Day, Kilometre, Flat rate, Litre or part of one, Metre or
  part of one and Kilogram or part of one. Documents show the abbreviation
  – "pcs.", "kit", "h", "day", "km", "flat", "l", "m", "kg" –; only
  Rentalars internally tells rental and sale apart. On an installation in
  German they are Stück (Miete), Stück (Verkauf), Set (Miete), Set
  (Verkauf), Stunde, Tag, Kilometer, Pauschal, Angefangener Liter,
  Angefangener Meter and Angefangenes Kilogramm, with the abbreviations
  "Stk.", "Set", "Std.", "Tag", "km", "psch.", "l", "m", "kg".
- **Tax accounts**: the accounts the Kontierung of the incoming
  documents (section 11, "Incoming invoices") books an amount to – an **account
  number** (digits only, 3 to 10, unique) and a **name** for each; an account
  can be deactivated, then it is no longer offered but stays where it is used.
  A list for SKR 03 comes with Rentalars; it is a suggestion to agree with the
  tax adviser. In Settings → Master data → Tax accounts, through the API at
  `/tax-accounts`.
- **Manufacturers** and **suppliers** – the suppliers are also the suppliers
  for subrentals, with name, contact, e-mail, phone, "our customer number
  there", note and their address ("Street and
  number", "Postal code", "City", "Country"): it appears on the page
  "Subrental at …" with route and map, and the collection in the trips of a
  project leads there (section 7). Rentalars links the correspondence of the
  subrentals to the e-mail address (section 9, "Subrenting"); "Show the
  subrentals at this supplier" leads to Planning → Shortages, filtered to
  them. Manufacturers and suppliers are also created
  along the way – while typing in the form of a model and in "New items"
  (section 4), in the dialog "New supplier" of a subrental (section 9). A
  supplier with subrentals or documents cannot be deleted, only
  deactivated.
- **Storage locations** as a tree: every location names what it is "part
  of" – "Halle 1 > Regal A > Fach 3", a case too –, one of them with the tick
  "default for new items" (section 4, "Storage locations").
- **Document types** for the project files: Stage plan, Rider, Running
  order, Hall plan, Contract, Order, Show file, Other
  (in German: Bühnenplan, Rider, Ablaufplan, Hallenplan, Vertrag,
  Bestellung, Showfile, Sonstiges). Per type it is set whether such files
  are shown to the crew. The type "Show file" is there for show files: files
  of this type name the console or software, the version and which one is
  the current show (section 11, "Files of the project").
- **Inspection types:** name, **"interval (months)"**, description ("what is
  inspected, to which standard") and the **categories** and **material
  models** they apply to. A new inspection type makes all of its items
  overdue until they are inspected or the last inspection has been entered
  (section 4, "Inspections"). The box **"electrical inspection
  (DGUV V3 / DIN VDE 0701-0702)"** marks the inspection of electrical
  devices: recording then asks for visual inspection, measured values,
  function test and test device, shows the limits and suggests the result
  (section 4, "Inspections"). The list of inspection types shows the box
  as a column. No inspection type is
  electrical until someone ticks the box.
- **Audits**: the **audit interval (months)** – 24 by
  default, 0 switches audits off – and the **quick picks for to-dos**, at
  most 12 (section 4, "Audits and to-dos").
- **Custom fields** and **Fieldsets**: fields with a value of
  its own per item, e.g. MAC address or inspection sticker, and their
  grouping per material model (section 4, "Custom fields"). Unlike the
  category-specific fields above, their value does not apply to the whole
  model but to the single piece.
- **Qualification types:** driving licences, instructions, certificates of
  people – name, description and **"valid for months"** (empty: does not
  expire by itself). From the date acquired and this number Rentalars works
  out the expiry date (section 12). A driving licence names
  under **"Driving licence classes"** the classes it covers, separated by
  commas, e.g. "B, BE" – by them the logistics checks the drivers (section
  7, "Logistics"). If no qualification type has classes, nothing is
  checked.

Master data that is in use cannot be deleted, only deactivated. It then
disappears from the selection lists.

**What a new installation brings along.** Besides the units above, the main
categories with their defaults:

| Category | Code | Own stock | New products |
|---|---|---|---|
| Sound, Lighting, Video/media, Rigging/truss, Cables (Ton, Licht, Video/Medien, Rigging/Traverse, Kabel) | T, L, M, R, K | yes | rental product, Piece (rental) |
| Sale (Verkauf) | V | yes | sale product, Piece (sale) |
| Material subrented from others (Extern zugemietetes Material) | E | no | subrental, Piece (rental) – with the product E-001 "Subrental" ("Zumietung") |
| Event technology services (Veranstaltungstechnik-Dienstleistung) | D | no | service, Hour – the service products of the job functions |
| Customer material (Fremdmaterial) – marked as "Customer material" | C | yes | rental product, Piece (rental), with owner and without price |
| Incidental costs (Nebenkosten) | N | no | incidental costs, Flat rate |
| Fleet (Fuhrpark) | FZ | yes | vehicle, Piece (rental) – the vehicles are the items (section 4, "Fleet") |

The German names in brackets are those of an installation in German. Plus
the **"Standard scale"** ("Standardstaffel") with 1.0 / 1.5 / 1.75 / 2.0 /
2.4 / 2.75 / 3.5 for 1 to 7 days and + 0.3 for every further day (section 5,
"Rental scales"), the storage location **"Main warehouse"** ("Hauptlager")
as the default for new items, the eight job functions Technician, Lighting
technician, Sound technician, Video technician, Stagehand, Warehouse,
Project planning and Other (Techniker, Lichttechniker, Tontechniker,
Medientechniker, Stagehand, Lager, Projektplanung, Sonstiges) with their
service products D-001 to D-008 – with the price and internal
costs per hour from the first-run setup
(section 12, "Job functions") –, the document types including "Show file",
and the surcharges with the rates according to § 3b EStG, switched off
(above, "Surcharges").

The notes below name the German start data.

The document type "Showfile" is visible to the crew and stands before
"Sonstiges".

The main category FZ "Fleet" – on an installation in German "Fuhrpark" –
has stock of its own, the product kind "vehicle" and the unit "Piece
(rental)" ("Stück (Miete)"). It brings no inspection
types for vehicles; you create those yourselves (section 4, "Fleet").

In the **product import**, the column "Unit" ("Einheit") may also say
"Piece" or "pcs." (in German "Stück" or "Stk."): Rentalars then takes the
piece unit the category presets – in Sound "Piece (rental)", in Sale "Piece
(sale)". A name that matches exactly always takes precedence.

### Document templates and text blocks

**Settings → Document templates:** per document type a heading,
introduction, closing text, additional footer line and "print the logo",
with placeholders such as `{project}`, `{due_date}` or – for the offer –
`{valid_until}` and `{validity_days}`; for the offer also the **"validity in
days"** a new offer suggests (14 by default). **Settings → Text
blocks:** paragraphs such as your rental terms, which are ticked when a
document is created. Both are described in section 11, "Templates and text
blocks". Look through the supplied texts once before the first document is
made. **"Template texts in English or German"** takes over the
supplied headings, introductions and closing texts in the other language –
own texts only if you tick them (also section 11).

### Accounting: Lexware Office and DATEV

*Looking and fetching the DATEV files is for whoever may read the
settings and see prices; changing for whoever may change the
settings (above, "Read only and accounting").*

**Settings → Accounting** brings invoices and cancellation invoices
into the accounts – one by one as vouchers to **Lexware Office**, or as a
**DATEV file** per period for the tax adviser. Both can be used together.

**Setting up Lexware Office:**

1. In Lexware Office, someone with administrator rights there creates an
   **API key** (Add-ons → Public API). The plan must include bookkeeping.
2. Here you enter it under **"API key"**. Rentalars stores it encrypted and
   never shows it again – only "stored, ends with …". An empty field keeps
   the stored key.
3. Switch on **"hand invoices to Lexware Office"**. With **"hand over at
   once"**, every new invoice and cancellation invoice goes across as soon
   as it is created; without the tick you hand them over by hand in the
   "Documents" tab of a project (section 11, "Handing over to Lexware
   Office").
4. **"book on the collective contact"** if you do not want to keep your
   customers individually in Lexware Office. Otherwise Rentalars looks up
   every customer there by customer number and creates them if they do not
   exist.
5. **"Check connection"** reports which company Rentalars is connected to
   and fetches the posting categories. Then, under **"Posting category per
   tax rate"**, you choose the category; "Einnahmen" (revenue) is the
   default. Go through the one for 0 % in particular with your tax adviser
   once.

Under **"Handing over to Lexware Office"** are the invoices that are waiting
or whose handover failed, with the error and **"Hand over again"**;
"Nothing waits and nothing failed." means everything is over there.

**Setting up DATEV** – ideally together with your tax adviser:

- **"consultant number"** (Beraternummer) and **"client number"**
  (Mandantennummer);
- **"fiscal year begins in"** – January if it is the calendar year;
- **"length of general ledger accounts"** – usually 4; debtor accounts have
  one digit more;
- **"chart of accounts"** – SKR 03 or SKR 04;
- **"Revenue accounts"** per tax rate. If empty, the standard accounts
  apply: SKR 03 8400 (19 %), 8300 (7 %), 8336 (0 %), SKR 04 4400, 4300,
  4336. They are automatic accounts, DATEV posts the VAT itself; ask your
  tax adviser before you change them;
- **"debtor accounts"** – **"one debtor account per customer"**: the
  customer number plus the amount **"added to the customer number"**
  (customer 10001 becomes debtor 10001 with 0, debtor 20001 with 10000);
  or **"one collective debtor account"** with its number, e.g. 10000.

**The DATEV export.** Under **"DATEV export"** you choose the period – the
previous month is suggested – and see how many invoices and cancellation
invoices fall into it. Then:

- **"Bookings (Buchungsstapel)"** – all invoices and cancellation invoices
  dated within the period, one booking per invoice and tax rate. A
  cancelled invoice and its cancellation invoice are two vouchers, each in
  the period of its date. The period must lie within one fiscal year.
- **"Debtors of the period"** – the customers of these invoices with
  address, VAT ID and payment terms, as they currently are in Rentalars.
  The tax adviser imports them before the first batch of bookings if the
  debtor accounts are still missing in DATEV.

The invoices **taken over from an old system** (section 11,
"Importing old projects from invoices") are left out of the export – they
were booked there. Tick **"Include invoices taken over from an old
system"** only if your tax adviser wants them in Rentalars' file.

Both files are CSV in DATEV format; the tax adviser reads them into DATEV
Rechnungswesen and finalises them there. If something is missing – the
consultant number, a revenue account for a tax rate, a customer number made
of digits –, Rentalars says so instead of delivering half a file.

**Please check the first handover and the first import.** The formats of
Lexware Office and DATEV are built from their published descriptions. Look
at the first voucher in Lexware Office and have your tax adviser check the
first batch of bookings before you rely on it.

### Change log

**Settings → Change log** shows every change to the data: who, when,
what – with the old and the new value. You can filter by kind of object,
user, period and text.

Entries by "system:…" come from Rentalars itself: `system:import` from the
import on the server, `system:setup` from the first-run setup. An import in
the browser is listed under the name of whoever started it. Entries by
"Aktualisierung …" were written by an update – for instance
the new prefix of the project numbers and every renamed
project with its old and new number, or the
surcharge rules that were made from the earlier rates. Some of these entries
name a reference as text, such as "D-001"; the log and the history
show such values as text.

The surcharge rates in an entry are only visible to whoever may also see
them under Settings → Surcharges (above, "Surcharges").

The log cannot be edited. By default it is kept for good; a shorter period
is possible under "Retention periods".

### Security log

**Settings → Security log:** who logged in and out and when, failed
logins (with the name entered), wrong two-factor codes, recovery codes used,
ended sessions, password changes, one-time passwords set, logouts after
inactivity – each with address and browser. Filters by kind and by name or
address. Below that, the latest changes to users, roles and tokens. Entries
are deleted after the period set, by default after 365 days (below,
"Retention periods").

### Access log

The change log says who *changed* something. For data protection, though,
it also matters who *looked at* something. **Settings → Access log**
records who

- opened customers, people and projects – for projects also their mails,
  files and documents,
- downloaded lists as CSV,
- downloaded the full export or a backup –

in the browser as well as through the API, with the time and the kind of
access. If the same person reads the same record several times within five
minutes, it counts once. What a person looks at about themselves is not
recorded.

You can filter by user, "Kind of object", "Access", period and text (name,
number or IP address); a click on an object in the list shows only the
accesses to it, "with everything that belongs to it" – for a project, also
to its mails and files. The log is also available as CSV. By default it is
kept for 180 days (below, "Retention periods"). When a customer or a person
is anonymised, the name disappears here too.

### Retention periods

How long Rentalars keeps logs and by-products is set under
**Settings → Company data and settings**. The daily maintenance then
tidies up.

| Setting | Default | Allowed |
|---|---|---|
| "keep the security log (days)" | 365 | 30 to 3,650 |
| "keep the change log (days)" | 0 – for good | 0 or up to 36,500 |
| "keep notifications (days)" | 180 | 7 to 3,650 |
| "keep results of background tasks (days)" | 7 | 1 to 365 |
| "keep the access log (days)" | 180 | 30 to 3,650 |

The mail log follows the period of the mails in the mailbox (section 14).
The runs of automations are always kept for one year (above,
"Automations").

Bear in mind with the change log: the "History" tabs on projects, items,
products and customers are also made from it. So a period shortens them as
well. The results of background tasks – import reports, label PDFs, full
exports – disappear together with their files. Created documents
(section 11) are not affected by any period; they always stay.

### Import and export

**Settings → Import and export** gathers everything that brings data
into or out of Rentalars.

**Importing** works for four lists, each from an **XLSX** or **CSV** file
with a heading row and one row per record. A CSV file may be in UTF-8 or –
as from Lexware, DATEV or older Excel – in Windows-1252; umlauts arrive
correctly either way.
A table may have at most 100,000 rows and 3 million cells (when reading: at most 300,000 rows, empty ones included – delete empty rows below the data –, and an XLSX file only up to column 199) and an XLSX file at most 200 MB unpacked; Rentalars refuses bigger files while reading (split them into several).

| List | Where else | An existing record is recognised by … |
|---|---|---|
| "Import material" | Material management → Import | its ID (guide [Importing the material list](operations/import.md)) |
| "Import products" | Material management → Import, tab "Products" | its **article number** |
| "Import customers" | "Import" above the customer list | its **customer number**, otherwise **VAT ID**, **e-mail address** or **name** |
| "Import people" | "Import" above the list of people | its **e-mail address**, otherwise **first and last name** |

Every import needs the right to create and edit in the module concerned;
the settings only shows the imports you may start. Next to them, there is the **"Export in the import format"** for every list you
may read (below).

**How it works – the same for all four:**

1. **Choose a file**, "Upload file". "Which columns are recognised?" shows
   which headings Rentalars assigns by itself.
2. **Assign the columns.** For each field you see the column of the file
   that Rentalars recognised, with the first values next to it. If something
   does not fit, choose another column or "– do not import –". Fields marked
   with * are required. For material, this step also asks
   whether the purchase prices of the file are net or gross (section 4,
   "Taking over the Excel list").
3. **"Dry run: check without writing".** It runs in the background; the page
   shows the progress, and you can carry on working. Afterwards it says what
   the import would do – "12 new, 340 changed, 5 unchanged" –, which rows
   have errors and which notes there are, and, below that under
   **"Rows of the file"**, every row with its outcome (below, "Every row in
   the dry run").
4. Only when the dry run has found **no errors** does **"Import now"**
   appear below the list. The import does exactly what the dry run showed,
   and also runs in the background.

**Every row in the dry run**. The list "Rows of the file" –
after the import "Imported rows" – gives for each row its number, the
record (ID, article number, name …), the outcome – **"new"**,
**"changed"**, **"unchanged"** or **"error"** – and the details: for a
changed row each field with **"previously"** and **"new"**, written as in
the change log, for an error the message, plus the notes of the row. Under
**"Show"** you choose "All except unchanged" (preset when there are
others), "All", "New", "Changed", "Unchanged" or "Errors", each with its
count; the field **"Row, ID or name"** searches, "Filter". There are 200
rows per page. Values you may not see – purchase prices, prices and
discounts, hourly and day rates – appear as **"not visible"**. After the
import the page shows the imported rows; filtering and paging work there
the same way.

**All or nothing:** if a single row has an error, Rentalars writes nothing.
Correct the file or the assignment and try again ("Use a different file"
starts from the beginning). Only what is assigned to a column is written;
all other details stay as they are. The change log lists the changes under
your name.

**What exists is updated, never duplicated:**

- **Products:** the article number decides – an existing product is
  updated, a new one created. Its letters name the main category; the column
  "Category" can name a subcategory. Unit, tax rate, product kind and billing
  mode are recognised by name; whatever the file does not give comes from the
  category's defaults. A unit without its part in brackets or with an
  abbreviation that several units share – "Piece", "pcs." – becomes the unit
  the category presets (section 16, "Master data"). The columns "Price",
  "Sale price" and "Maximum discount" need the right "See prices and
  calculation". Every product has exactly one price (section
  5, "Creating a product"): for a sale product the column "Price" fills its
  sale price if "Sale price" is empty; a sale price for any other product
  the import skips with a warning. For customer material, the column **"Owner"** names the
  customer – by customer number or name; if several customers have the same
  name, use the customer number. A product in a category for customer
  material needs an owner and no price; an empty cell means "own material"
  (section 5, "Customer material"). A new **service** brings its job
  function along; the dry run rejects a name that a job function already
  has. The import recognises the kind "incidental costs" by that name, the
  kind "vehicle" by "vehicle", "Fahrzeug" or "Fuhrpark"; their
  rates are in the columns "Vehicle type", "Price per km", "Trailer
  surcharge per km" and "Trailer billed" (price right), their costs in
  "Internal cost per km" and "Internal cost per day" (right for purchase
  prices).
- **Customers:** each row looks for the customer it describes – in this
  order by **customer number**, **VAT ID**, **e-mail address** (of the
  customer or of a contact) and **name**. For the name, upper and lower case,
  punctuation, legal form and the spelling of umlauts do not matter: "Müller
  GmbH" is "MUELLER gmbh". A private person is never matched to a company or
  the other way round. A customer that is found is **added to rather than
  duplicated**:
  - **Empty cells overwrite nothing** – what Rentalars already knows stays.
    (So a field cannot be emptied through the import.)
  - Contacts are added if there is none with the same name or the same
    e-mail address yet, otherwise they are completed; the same goes for a
    delivery address.
  - If the address has changed, the previous one is kept as a further
    billing address.
  - If Rentalars finds a customer by VAT ID, e-mail or name who has a
    different number in the file, they keep their number in Rentalars.

  A row without a match becomes a new customer: with the number from the
  file if Rentalars does not know it yet – so customers from the old program
  keep their number –, otherwise with the next number. If several customers
  match, Rentalars would rather create a new one and says which ones were
  possible. The **dry run** shows for each row what happens: new, merged with
  which customer and how it was recognised ("merged with 10042 "Kulturverein"
  (found by the e-mail address)"), or unchanged. The column "Ansprechperson"
  (contact person, with e-mail and phone) creates or updates the main
  contact. "Default discount %" needs the right to see prices.
- **Customers from Lexware:** upload the **contact export** of Lexware (CSV)
  unchanged. Rentalars recognises its columns by itself – "Firmenname",
  "Straße 1", delivery address ("… 2"), Steuernummer, USt-IdNr.,
  "Ansprechpartner 1 Vorname" with salutation and so on. Address 1 becomes
  the main address, address 2 a delivery address; a second e-mail address or
  phone number ends up in the note. Rentalars does not take over the
  supplier number, and the report says so. Lexware also counts customer
  numbers from 10001 – if only the number matches in a row, but neither the
  name, VAT ID nor e-mail, the dry run warns, because then it is probably a
  different customer.
- **Personnel:** a person is recognised by their e-mail address, otherwise
  by first and last name; those recognised are updated, the others created.
  The name can be in one column ("Nachname, Vorname" – last name, first
  name – as in the export, or "Vorname Nachname") or in two. The column
  **"Funktionen"** (job functions) lists the job functions separated by
  commas. Rates of their own follow a colon, the hourly rate and, after a
  slash, the day rate: `Tontechnik: 35,00/280,00, Licht: /250, Rigging` –
  Tontechnik at €35.00 an hour and €280.00 a day, Licht with a day rate
  only, Rigging without rates of its own (the guide values apply). The job
  functions must already exist under Personnel → Job functions. Rates need
  the right "See hourly rates and personnel costs". If a person already has
  the job function, different rates from the table apply from today; what
  the row does not mention stays. The import never takes a job function
  away. Like people created by hand, newly created people get their login
  with the role "Crew" or "Freelancer", but no invitation – you send that
  afterwards (section 16, "Users").

**There and back.** A list you download as CSV from the product, customer
or people list (section 2, "Lists") is recognised by the import again:
download, change it in the spreadsheet, read it back in. Downloaded with
"CSV with all columns", each of the three lists can also be read back in
unchanged – the import assigns the headings by itself. The export in the
import format is made for exactly this (below).

In the browser there is no limit on the number of rows. Whoever looks after
the server can also import lists there:
`rentalars import_data products|customers|people FILE` (guide
"Operation").

**Exporting.** Every list can be downloaded as CSV (section 2, "Lists"),
as you see it.

**Export in the import format**. For each of the four
imports – material, products, customers, people – there is the link
**"Export in the import format"**, here next to the import and at the top
of the import page itself. It downloads a CSV file with **exactly the
columns and headings of the import**, in **plain text**, so that you can
work on with it even without Rentalars:

- names and numbers instead of internal IDs – category and storage location
  as a path ("Ton > Mikrofone", "Halle 1 > Regal A"), supplier, unit and
  tax rate by their names, the owner of customer material by the customer
  number, a person's job functions with the rates that apply today, as the
  import reads them;
- dates as `31.12.2027`, numbers with a decimal comma and no thousands
  separator, "ja" and "nein", choices by their German names – in German
  like the headings of the import, also if you use Rentalars in English;
- for material one column per custom field, headed with its name (section
  4, "Custom fields"), and the column "Schutzklasse" with the
  class that applies to the item – its own, else its model's – as `I`,
  `II` or `III` (section 4, "Taking over the Excel list").

Columns with prices, purchase prices or hourly and day rates are only in
it if you may see them; otherwise the column is missing – for people,
"Funktionen" then names the job functions without rates –, and importing
such a file leaves these values as they are. Text that a spreadsheet
would run as a formula gets an apostrophe in front; the import takes it
away again. **Imported again, the file changes nothing** – the dry run
calls every row "unchanged"; edited in a spreadsheet, it changes what you
changed. What the import does not know is not in it – such as a fourth
contact person of a customer or the lines of the projects; that is what
the readable export of all data is for. Whoever may read the list may
download it. Even 20,000 items are there in a few seconds.

**All data at once** – the **"Readable export of all data"** – is under
**Settings → Backup** (below, "Backup and encryption").

### Background tasks

Whatever takes longer, Rentalars runs in the background so that no page has
to wait: **dry runs and imports**, **more than 240 labels**, the **full
export**, **backups from the browser**, **handing an invoice over to
Lexware Office** and **reading old invoices** for the
import of old projects (section 11) and the run of the **automatic AI
summaries** ("Run now", section 14). You can carry on working meanwhile; when the task is
finished, you get a notification ("Ready: …" or "Failed: …").

**My account → "Tasks in the background"** lists your tasks of the last few
days with "Started" and status – "waiting", "running", "ready" or "failed".
A click shows the progress while it runs, and afterwards the result with
"Download" where a file was made. A task and its result can only be seen by
whoever started it – administrators do not see other people's tasks either.
After the retention period (seven days by default) Rentalars clears them
away together with their files.

### Self-check

**Settings → Self-check:** the state of the installation – versions,
database, file permissions, e-mail, last backup, storage, security settings
and errors of the last seven days. Every row has ✓ (fine), i (note), !
(warning) or ✗ (error). "Send a test mail to me" checks sending, "Check
again" checks once more. If no mail server is set up, the row "System mails"
under "E-mail" warns: invitations, password links and notifications then do
not go out; the test mail reports "Not sent – no mail server set
up." instead of "sent" (section 14, "Without a mail server"). What the
individual points mean and what to do is in the guide ["Operation"](operations/operation.md); Rentalars
also reports errors to the administrators by itself.

There is the group **"Gateway"**: if a gateway is connected, it shows
its address, whether it answers (error if the last answer is older than 90
seconds – then the service of the server is not running), the last error and
the number of paired and revoked apps. Without a gateway it says "none – the
apps reach the server directly".

The group **"Versions"** also names **ffmpeg**, the program
with which the server makes videos for the chat smaller; if it is missing,
the row warns – then only videos are refused, photos work. And the row
**"NGINX upload limit"** warns if NGINX accepts smaller files than a video
in the chat may have (200 MB). Both are dealt with by whoever looks after
the server (guide ["Operation"](operations/operation.md)).

The group **"Server"** shows what Rentalars runs on:

- **"Processors"** – how many, and the load of the last 1, 5 and 15 minutes;
  if the load is above twice the number of processors, requests wait for a
  processor, and there is a warning;
- **"Memory"** – total and free, with a warning when it gets short;
- **"Memory used by Rentalars"** – how much the processes of the application
  take up;
- **"Host name"**, **"Network"** per interface with addresses and the amount
  of data received and sent since the start, **"Running time"** since the
  last restart.

**Raspberry Pi.** Rentalars also runs on a Raspberry Pi
4 or 5 (64-bit, from 4 GB of memory, ideally with an SSD) – with Ubuntu
Server for the Pi or with Raspberry Pi OS based on Debian 13. How to prepare
it and what is different is in the guide ["Installation"](operations/installation.md), section "Raspberry
Pi". On a Pi the self-check shows the row **"Device"** with the model under
"Server" – with a note if it has less than 4 GB – and the note **"SD card"**
under "Storage" if the database, data folder or backups are on the SD card.

**Security → HTTPS.** Under "Security", the row "HTTPS" shows the address of
the installation with ✓. A server only starts with an address
that begins with https:// – unless the operator has deliberately allowed
unencrypted HTTP in the configuration file (`allow_http = yes`); then there
is a warning here: passwords and sessions travel through the network
unencrypted, unless a server in front encrypts them.

**"Connections to other servers"**. Rentalars connects to
linked calendars, CalDAV calendars, webhooks, the mail servers of the
mailboxes and, the interfaces of the AI only if the address
does not lead into the internal network – so
not to this computer, not into private networks (such as 192.168.x.x or
10.x.x.x) and not to the server itself. A NAS or a Nextcloud in your own
network still works if the operator allows it in the configuration file
(`[network] allow_internal`). Under **"Internal addresses"** this group
names every setting that leads into the internal network without being
allowed – with the address the name belongs to and the kind of network –,
and under **"Allowed internal addresses"** what is allowed. Rentalars
deletes or changes none of it; the setting fails until the operator allows
the address or someone changes the setting.

The button "Backup and encryption" leads to the page of that name.

### Backup and encryption

**Settings → Backup** or **→ Encryption** – one page with two parts, with a third: the readable export of all data (below).

**Backup.** Every night at 2:30 the server backs up the database and files
by itself to `/var/backups/rentalars`. The page shows when the last nightly
backup was made and whether it is encrypted. Copy these files regularly to
another device – a backup on the same disk does not survive losing it.

**Consistent.** The backup writes the database first and the files
after it. A file that someone deletes in between would still be named in the
database of the backup and be missing from the files. So a deleted file first
moves for **seven days** into the folder `.deleted` of the files, which the
backup takes along; the daily maintenance deletes it for good afterwards. So
everything the database of a backup names is in that backup.

**"Back up now"** writes the same file as the nightly backup – database, all
stored files, the configuration file and the version – for **downloading**,
for example before a larger change. That takes a while and runs in the
background; it appears under **"Your backups from the browser"** as soon as
it is ready. Whoever may delete in the settings may create one; **only
whoever created it can download it**. After the period for background tasks
(seven days by default) Rentalars deletes it; the nightly backup does not
take it along. On the server you restore it with `sudo rentalars restore
FILE`.

- **If the backups are encrypted**, the dump of the database never lies
  unencrypted on the disk either – not even for a moment in the
  temporary folder –, and the file gets **a key of its own**: it
  is shown with the finished backup ("Key of this backup – click to copy:")
  and only to you. Keep it separate from the file; without it the backup
  cannot be opened, by anyone. Restore with
  `sudo rentalars restore FILE --key-file KEYFILE` – or type in the
  key when the command asks for it.
- **If they are not**, the page says so: the file contains everyone's
  personal data and the access data of the database – keep it as safe as
  the server itself.

**Encryption.** The page shows whether the **database** and **new backups**
are encrypted, whether the last nightly backup was, and where the
**recovery key** is. If the database runs on another server, that server
decides on the encryption of its files.

There is deliberately no button to switch it on ("Why there is no button
for it"): switching it on changes the settings of MariaDB, restarts the
database and stores a key that only root may read. Rentalars itself
deliberately runs without these rights – so even someone who takes over an
administrator account could neither change the database server nor read the
key. **"How to switch it on"** explains the command `sudo rentalars
encryption enable` on the server (as root): it first writes a backup of the
current state, stops Rentalars briefly and has MariaDB encrypt every table,
then compares every table with the state before – Rentalars only starts
again when not a single value differs – and encrypts the existing and all
future backups. At the end it shows the recovery key – write it down and
keep it separate from the server. Once encryption is switched on, the page
shows instead of the instructions how to display the key on the server
again. More in the guides [Encryption](operations/encryption.md) and
[Backup](operations/backup.md).

**Readable export of all data.**
**"Make a full export"** writes all data and files in
open formats into **one ZIP file**:

- `json/` – every table as a JSON file;
- `csv/` – the same tables as CSV for the spreadsheet, one column per
  field, references to other tables as internal IDs;
- `dateien/` – all stored files: project files, mail attachments,
  documents, photos, logs, also photos and videos from the
  chat;
- `LIESMICH.txt` – what is in the archive and what is missing.

**Secrets stay out** – passwords, the keys of the two-factor login, API
tokens, the passwords of the mailboxes, the links of the linked calendars,
 the addresses of the calendar links of products, models and
items, the API keys of Lexware Office and of the AI interfaces; the webhooks are
left out entirely (their address can itself be a secret link). Everything
else is in it, including everyone's personal data – and the file is
**never encrypted**, even if the backups are: keep it as carefully as a
backup. Only administrators may create the export (Settings with the level
"delete"). It is made in the background; when it is ready you are told and
download it under My account → "Tasks in the background" – for seven days,
unless the period has been changed. Only whoever started the export can
download it, not even another administrator. On the server the same works
with `rentalars export_data`. Single lists in the format of their import
are under Settings → Import and export (above).

**Export or backup?** Both contain all data, but they are for different
things:

- **The backup restores Rentalars.** It holds the whole database with all
  secrets, the configuration and all stored files, is encrypted if
  encryption is switched on, and is put back on the server as a whole –
  with `sudo rentalars restore`.
- **The readable export is for reading** – by other programs or for your
  own archive: a ZIP file with JSON, CSV and the files, without passwords
  and keys, with the internal IDs, never encrypted. Rentalars cannot be
  restored from it – at most the data can be loaded into a freshly
  installed Rentalars of the same version, without passwords and
  mailboxes.
- **The export in the import format** is one CSV file per import in plain
  text, without internal IDs, that can be imported again (above, "Import
  and export").

### Gateway: pairing apps

Under **Settings → Gateway** you pair an app with the server when the apps come through the
Rentalars Gateway – without SSH. At the top you see whether the gateway answers. Under **"Pair an app"** you choose
the account (the app has its rights), optionally a name for the device and how long the code is valid (1, 5 or
10 minutes) and click **"Make a pairing code"**. The page shows the code as a QR code and as text; it works once
and is gone when you leave the page. In the app: add an installation → "Pair with gateway" → scan the code or paste
the text. Below are the paired devices with account, pairing and last use; **"Lock out"** locks one at once, and
the app has to be paired again. Administrators who may delete in the settings can pair and lock out; both are
written to the change log. Connecting to the gateway itself stays a command on the server (guide "Gateway").

### Server address and certificate

Under **Settings → Server address and certificate** you see
the address under which Rentalars is reached, which name NGINX serves and
which certificate it presents – who issued it and how long it is valid.
Below are earlier changes with their result.

**You prepare a new address here** (whoever may delete in the settings may
do so – a private key is uploaded). Under **"Prepare a change"** you enter
the **new host name**, without `https://` and without a port, and choose
where the **certificate** comes from:

- **Let's Encrypt** – with an e-mail address for notices about the
  expiry. The name must be in the public DNS, and port 80 must be
  reachable from the internet.
- **Self-signed certificate** – for trying things out; browsers warn.
- **Own certificate** – the certificate with its chain and the private key
  without a password, both as PEM files.
- **A server in front encrypts** – another server in front of Rentalars
  takes care of the certificate; only the name changes.

**"Redirect the old address to the new one"** is preset: whoever calls up
the old address lands at the new one – over HTTPS as long as the old
certificate is valid for the old name.

**"Check and prepare"**: Rentalars checks what it can check from here –
whether the name points to this server in the DNS (behind a router it says
when it cannot be sure), whether NGINX answers on ports 80 and 443 and,
for your own certificate, whether key, chain, names and expiry fit. Each
result is listed under "What Rentalars could check".

**Then the page shows exactly one command**, such as
`sudo rentalars address apply 3f2a…`, with "Copy" and, below it, what it
will do. Nothing changes until it runs on the server. Give it to whoever
looks after your server, or run it yourself via SSH; with `--dry-run` it
only shows what it would do. The command checks everything again, first
backs up configuration, NGINX and certificates, and restores the previous
state on any error. You then see the result here: "Applied on … by …" or
"The command failed on …" with the error. A newer preparation replaces the
previous one; "Discard this change" withdraws it, and its command no
longer works.

**Why there is no button for it:** a new address changes the web server,
requests or installs certificates and restarts Rentalars. That needs root
on the server. Rentalars runs without these rights on purpose and never
stores access data for root – even someone who took over an administrator
account cannot change the server.

**Afterwards** everybody logs in again at the new address, and links in
new e-mails – invitations, password resets, deployment requests – use the
new address. Calendar subscriptions and printed QR codes keep the old
address; they work as long as the old address redirects. The Rentalars app
on the phones needs the new address.

### API tokens – Rentalars for other programs

Everything the interface can do, another program can also do through the
programming interface (API): a warehouse scanner, a spreadsheet, your
website – and the Rentalars app for Android (section 2). You find the full
description under **Settings → API documentation**; it opens in a new
tab so that the settings stays open.

A program logs in with a **token**. Every user creates their own, under **My
account → API tokens**:

- Say what the token is for ("Lagerscanner Halle 1").
- **"Read-only"** and **"Limit to modules"** narrow it down. A token never
  has more rights than you do yourself.
- The token is **shown exactly once**. Copy it straight away; Rentalars only
  stores a check value and cannot show it to you again.
- "Revoke" makes a token invalid at once.

Treat a token like a password.

**Tokens create other tokens only within limits.** A program can use its
token to create further tokens through the interface – but never with more
than it has itself:

- A token **limited to modules** – like the app's – cannot create tokens,
  and through the interface it sees and revokes only itself, not the other
  tokens of your account ("A token limited to modules cannot create tokens.
  Create tokens in the browser.").
- A token with an **expiry date** only creates tokens that expire no later
  than it does.
- A **"Read-only"** token changes nothing: it creates and revokes no tokens, ends no sessions and changes no settings of its user (answer 403).

In the browser, under My account → API tokens, you create tokens as
before.

**Calls per minute.** So that a program that gets into a muddle does not
slow down the whole system, every token may by default make **600 calls per
minute**. Rentalars answers further calls until the end of the minute with
"too many requests"; the program waits and then tries again. You set the
limit under Settings → Company data and settings ("API calls per
token and minute"); 0 switches it off. What else a program needs to know –
for example how it avoids duplicate calls and overwritten changes – is in
the API documentation. An Idempotency-Key applies per token or
per session: the stored answer only comes after logging in and checking the
rights as for a new call, and the same key with different content gives
409. Changes with `If-Match` compare and write in one step; two simultaneous
changes to the same version do not overwrite each other.

**Project numbers in other programs.** If a program has stored project
numbers with "P-" (`P-2026-0042`), it now
gets the number without (`2026-0042`). The number with "P-" is in the field
`former_number` of every renamed project, and querying the projects with
`?number=` finds a project under either number.

**Service cases in other programs.** The list of
projects does not return service cases unless the program asks for them
with `?kind=`; they are under `/service-cases`. Every project names its kind
in the field `kind` – `project` or `service_case` –, as do the webhooks
(below). A service case needs a customer through the interface
too – unless it is internal (`is_internal`).

**Invoices in other programs.** Every project names the state
of its invoice in the field `invoice_state` – `open`, `invoiced` or
`not_needed`; empty without the right to see prices, and for projects
without an invoice of their own. `POST /projects/{id}/invoice-status` with
`invoice_status` `issued` ("Invoice issued"), `not_needed` ("No invoice")
or empty sets it – with the right to edit the project and to see prices
(section 11, "Invoices still to be written").

**Purchases and products in other programs.** Available are, among others,
`POST /purchases` and `POST /purchases/invoices` (entering a purchase and
reading the invoice), `POST /products/{id}/duplicate`,
`POST /projects/{id}/crew-lines/bulk` (several crew lines),
`POST /time-entries/{id}/correct` (correct and approve) and
`GET /accounting/documents` with `/accounting/documents/totals` (the
outgoing documents). A product accepts only one price: a sale price on a
rental product, a price on a sale product and `is_sale` for a line with a
rental product give 400. Without the special right "See availability of
material", planning and lines deliver `availability` and `shortage_total`
as `null`, and `/availability`, `/shortages` and `/utilization` answer
403.

**Audits and to-dos in other programs.** Available are audits and to-dos
(`/material-items/{id}/audits`, `…/todos`, `/material-todos`,
`/material-audits/due`, `/audit-settings`; on items `last_audit`,
`next_audit`, `audit_due`, `open_todos`; `POST /material-todos/done` with
`{"todos": [12, 13]}` marks several to-dos done at once like "Mark chosen
to-dos done" under Open points → Material with to-do – at most 2,000, with
write access to material – and answers with `done` (how many were open
and are done now), `already_done` (how many were done before) and
`not_found` (the IDs no to-do has)), custom fields (`/custom-fields`,
`/custom-fieldsets`, `fieldset` on material models, `custom_fields` – name
→ value – on items), photos and videos in the chat (`attachments`, `POST`
with files), the lock of the correspondence (`locked`,
`PATCH /projects/{id}/mails/{mail}/lock`), `GET /projects/{id}/access`,
`/projects/{id}/relations`, `/projects/{id}/phases/{phase}/staffing`,
`follow` when moving and `GET /imports/{kind}/export` (the export in the
import format). Changed: a message with a lock does not exist for a program
without the right "See prices and calculation" (404); open messages are
also read by the crew planned in that has accepted or is planned firmly.
An answer (`answer_to`) to a message with a lock gets the lock when
`locked` is left out, and `GET /projects/{id}/history` names the subject
of a mail or note, like the page, only to those who may read the message.
The full list is in the API documentation.

**Automations in other programs.** Available are
`POST /automations/restore-defaults` (create the missing automations that
came with Rentalars; 201 with those created, 200 with an empty list if
none was missing), `POST /material-items/{id}/inspections/check`
(measured values against their limits, nothing is stored),
`GET /inspections/{id}/report` (the test report as PDF) and `GET`, `POST`
and `DELETE` on `/products/{id}/calendar-link`,
`/material-models/{id}/calendar-link` and
`/material-items/{id}/calendar-link` (the calendar link: read – the
address `url` only for whoever may change it –, create or replace – 201
new, 200 replaced –, deactivate). New fields:
`default_key` and `default_changed` on automations (read only),
`protection_class` on models, `protection_class_override` and
`effective_protection_class` on items, `is_electrical` on inspection
types, on inspections the measured values (`protection_class`,
`cord_length_m`, `test_device`, `visual_check_passed`,
`pe_resistance_ohm`, `insulation_resistance_mohm`, `pe_current_ma`,
`touch_current_ma`, `function_test_passed`), `evaluation` and
`report_url`; in the proposal of a read invoice `total_net`,
`total_gross`, `currency` and per position `serial_numbers`,
`category_id`/`category`, `product_id`/`product` and `hints`; on the
notification preferences `label` and `category_label`. An electrical
inspection reported "passed" although the measured values speak for
"failed" needs a `note`, otherwise 400. What existed stays.

### Webhooks – notifying other programs

*Looking is for whoever may read the settings; creating, changing,
testing and seeing the secret for whoever may change it; deleting for
whoever may delete there.*

Through the API, another program asks Rentalars. A **webhook** goes the
other way: it tells another system – ERP, chat, n8n – by HTTP by itself when
something happens in Rentalars. That way the other system does not have to
keep asking.

**The events:**

| Event | When |
|---|---|
| "Project created" | a project is new, in any status |
| "Project status changed" | by hand or because material was issued or came back |
| "Material issued" | material of a packing list went out, also in parts |
| "Issue taken back" | an issue made by mistake was taken back |
| "Material returned" | more material was ticked as back – one row or "Everything is back", in the browser or from the app (when the app syncs, once per sync) –, or the return is finished, by itself after "Book the return" or by hand |
| "Material handed over between subprojects" | a handover was booked or taken back (section 10) |
| "Time entry approved" | per approved entry |
| "Approval of a time entry taken back" | |
| "Document created" | any kind, also a cancellation invoice |

**Creating a webhook:** Settings → Webhooks → **"New webhook"**.

1. **"Address (URL)"** of the receiving system, beginning with `https://` or
   `http://`. Internal addresses – this computer, private
   networks such as 192.168.x.x, the server itself – only work if the
   operator allows them in the configuration file (`[network]
   allow_internal`); otherwise the form rejects an IP address or `localhost`
   straight away, and a name fails on delivery (section 16, "Self-check").
   Username and password do not belong in the address – the receiving system
   checks the signature instead.
2. A **description** of which system it is ("ERP", "n8n: Lager").
3. Tick the **events**, "Save webhook".
4. After saving you see **the secret once** – copy it into the receiving
   system now. Later, **"Show secret"** shows it again; **"Create a new
   secret"** replaces it at once, and the receiving system rejects the
   messages until it knows the new one.
5. **"Send test"** sends a test message straight away and shows the answer.

**What the receiving system gets:** every event comes as a `POST` with JSON
– version, the ID of the delivery, the event, the time and the data of the
event, such as number, name and status of the project and its kind `kind` (`project` or `service_case`). **Prices and costs
are never part of it.** The header `X-Rentalars-Signature` carries `sha256=`
and the HMAC-SHA256 of the content, made with the secret; the receiving
system calculates it itself and only trusts messages where both match. The
events, each with an example, are in the API documentation under
"webhooks".

**Deliveries.** On the page of a webhook, **"Deliveries"** lists all
messages of the last 30 days with content, attempts and the start of the
answer. An answer 2xx counts as delivered. Whatever fails, Rentalars tries
again after 1 minute, 5 minutes, 30 minutes, 2 hours and 12 hours; after
that the delivery is set to "failed", and **"Send again"** sends it once
more. Rentalars does not follow redirects – enter the final address.

**Switched off.** If **10 deliveries in a row** fail for good, the webhook is
switched off and the administrators get a notification. Then check the
receiving system, send a test and switch the webhook on again under "Edit"
(tick "Active"); the waiting deliveries then go out. As long as a webhook is
off, Rentalars does not queue new events for it.

Webhooks are not in the full export (above, "Backup and encryption"). Whoever
may read the settings also sees in the deliveries the names of people
from approved time entries.

---

## 17. What this version cannot do yet

The requirements catalogue lists every requirement as "must", "shall" or "may". All "must" and "shall" requirements have
been built. What the catalogue lists as "may" belongs to **stage 10 – further extensions** and comes one by one, as needed;
among others, login through LDAP, scanning with the camera, accessory and replacement suggestions, built-in bulk material
and the own price of a freelancer have been built from it. This chapter says what is missing:

- Login through an **external identity service** (OIDC or SAML). Login
  through LDAP or Active Directory is available (section 16,
  "Directory (LDAP)").
- **Planning on trial:** a "Save" switch with which one tries changes in
  the planning and then applies or discards them (PRJ-129, "can"). It is
  left out on purpose: everything is still saved at
  once. A saved planning state to go back to would be the simpler form.
- **Calendar feeds (iCal)** for projects. The calendar of your own
  deployments already exists (section 12), and calendar links
  for products, models and items (section 4, "Calendar link").
- **Customer-specific prices** or price groups. (Accessory suggestions
  when adding a product and replacement suggestions for a shortage exist
, section 5 and section 7.)
- Rentalars **as an installable web app** – the logo as an icon on the home
  screen already exists.
- Rentalars **as a container**.
- A **contract per customer** for the monthly statement of the service
  cases – flat rate per month, hours included, rate beyond them and a
  reminder of the statement – and **text blocks for mails** per mailbox.
- Noted from use: **notifications** about open shortages or open
  items a few days before the start of a project; **suggestions for project
  templates** from several similar projects by an AI (listed as "later"
  under Settings → AI); keeping the **job functions** with the products
  instead of under personnel, and separating **services** from the other
  products – job function and service product already
  belong together 1:1.
- Noted from use: with a **deployment request to a freelancer**,
  they name their price themselves in their answer instead of confirming a
  given rate – built as the price offers of freelancers (section
  12), off until you switch it on.
- **Handing the tax accounts** of the Kontierung to the accounting program
  (the accounts are kept; the format of the hand-over is open), and
  a **DATEV export** of the asset register and the sales from stock.

The exact assignment is in the requirements catalogue, chapter 10.

On personnel in particular: planning and calculation is in **hours** or
**days**, with a higher rate above a limit of hours per day and with
surcharges according to rules you set yourselves (section 12). The
holidays – those of a federal state and your own – apply equally to all
projects, not depending on the venue. The surcharges appear in the
planning, the price overview and documents, not yet in the time report and
not in the crew's overview; Rentalars does not do payroll. That a **job
function can require qualifications** and Rentalars warns when planning if
a certificate is missing or has expired belongs to stage 10; until then the
page and the timeline of a person show what is expiring (section 12). Only
the driving licence class of a driver is checked, by the
logistics (section 7, "Logistics").

On time tracking: without a network you record times with the Rentalars app
for Android (section 2); expenses are not in the app yet, but in the browser,
on a phone too. Splitting a period across several job functions works in
the browser; whether the app can do it depends on its version – Rentalars
accepts times without a split from it as before. A running stopwatch can
only be split after stopping it. You choose the people involved in a
service case from a list, without suggestions while typing. Approved
expenses appear in the totals of the planning and the project list, not in
the price overview. The hints at unusual times do not stop anything and do
not replace a record of working hours (section 13).

On maps and trips: Rentalars does not calculate travel times – Google Maps
plans the route after the click. It calculates distances only with the
route service the operator sets up on the server, and only as a suggestion
for the planned kilometres of a vehicle (section 7, "Logistics"). Rentalars
does not suggest an address while you type (the map search of
OpenStreetMap does not allow it). The trips appear in the schedule and the
overview, not yet in the PDF of the deployment overview.

On the logistics: a booking for which no vehicle has been chosen yet does
not appear in the utilization of the fleet. Licence plate, seats and the
other vehicle data do not go through the import and export of material;
you enter them on the item. Trips you added by hand are not copied when
duplicating – and so neither are the vehicles on them. The calendar link
of a vehicle (section 4, "Calendar link") shows its blocked periods and
inspections, not its bookings in the logistics.

On the chat: it is not in the search, not in the webhooks and not in the
Rentalars app. Appointments in the timeline and deployments in the personnel
plan are dragged with a mouse or pen, not with a finger, and a deployment
not onto another person (section 15). Conflicts are shown by the personnel
plan, the week of the availability, the timeline of a person and, the timeline of the schedule, not by Planning → Timeline.

On taking back: if only part of a row comes back, you cannot choose which
items they are; they only become free when the row has been taken back
completely (section 10). Issuing and "Book the return" only work in the
browser, not in the app.

On correspondence: Rentalars reads your mailboxes at your provider, with
user and password; logging in through Microsoft 365 or Google without a
password (OAuth) belongs to stage 10. So do several tags in one subject,
additions to the tag and text blocks for mails, also per mailbox; a
signature of its own per mailbox exists (section 14), the text
blocks of the documents (section 11) only apply there. As the sender,
Rentalars only offers addresses of the mailboxes of the correspondence, so
that answers come back. Rentalars does not create a
project by itself from an inquiry without a tag – only a service case if
the address it went to is set up that way (section 14, "Further addresses
of a mailbox"); an automation can answer it and notify someone
(section 16). In the inquiries, "As a project" or "As a service case" turns
it into a project or a service case with one click, or you take it over
into an existing project – or forward it with the tag in the subject to a
mailbox of the correspondence.

On subprojects: the time report, "My times", the timesheet and the pages of
a product and of an item name a subproject only by number and name – the
ending "-1" shows that it is one.

On the languages: calendar subscriptions, also the calendar
links of products, models and items, and CalDAV, webhooks, the history
and the change log, and the sample data appear in the language of the
installation; the runs of automations and the values of their
placeholders in the language of documents, because automations write to
customers. In a notification about a changed project, "what changed"
is in the language of whoever changed it. The import recognises the
columns of a file by their German headings; if a file comes from the
English interface, you assign the columns yourself in the step "Assign
the columns" (section 16, "Import and export"). Rentalars knows English and
German, no other language.

On the AI: it summarises the correspondence of a project or service case,
suggests replies and, if wished, reads purchase invoices,
nothing else; it writes the reply draft in the
language of the mail you are answering. How fast the local AI is depends
on the server; on a Raspberry Pi a summary takes a few minutes.

On purchases: "Read the invoice" reads only PDFs with text – not scanned
invoices or photos; there is no text recognition. A new model that "Enter
a purchase" creates keeps its stock as individual items; create bulk
material as a model beforehand. When reading, Rentalars fills in a
product only if the AI names it by its article number or by a name no
other product has; it offers the AI at most 40 products – with many
products those whose names share words with the invoice. When a model is
duplicated, taking over the inspection types is not recorded in the
copy's history.

On the electrical inspection: you type the measured values – Rentalars
does not read test devices or their files; attach a protocol of the test
device as a file. The limits are those of DIN VDE 0701-0702 for
protective conductor resistance, insulation resistance, protective
conductor current and touch current; they cannot be changed.

On working on a service case: whoever works on a case only as the person
responsible or as someone taking part does not upload files there, does
not file mails and does not move mails to another project; writing and
answering mails works. Without access to the projects, the tabs Documents,
Access and History of the case are missing for them.

On the server address: a Let's Encrypt certificate with a DNS record as
proof (for servers that can only be reached over VPN) cannot be prepared
from the settings, nor can a port other than 443. Removing the redirect of
an old address again is only possible on the server (guide ["Operation"](operations/operation.md),
"Changing the server address and certificate").

On incoming invoices and fixed assets: Rentalars reads
invoices from PDFs with text; scans and photos are kept but not read, there
is no text recognition (section 11, "Incoming invoices"). The depreciation
follows **simplified standard rules and is no tax advice**: straight line by
month, low-value assets written off at once; degressive depreciation,
special depreciation, the half-year rule and a collective item for
low-value assets are not covered. Ask your tax adviser before you use the
figures. The asset register and the sales from stock have no DATEV export,
and an invoice written for a sale from stock is a free draft that is not
linked to the sale. Handing the tax accounts of an incoming invoice over to
the accounting program is not built.

On old projects from invoices: only PDFs with text, in euros, and no credit
notes. **How well the AI reads real invoices from other programs has not
been tried enough**; the preview shows what it read, and nothing is created
before you confirm. The imported projects are closed, have no mails,
tasks, reservations or availability, and are not part of the live invoice
numbers (section 11, "Importing old projects from invoices").

On scanning: the camera needs a secure connection (HTTPS) and a browser
that can read codes by itself – Chrome, Edge or Chrome on Android; in
Firefox and Safari you type the code or use a hand scanner that types it.
Scanning has been tried with simulated codes and scanners, **not yet with
the camera and the hand scanner of a real warehouse** (section 4,
"Scanning labels and codes").

On built-in bulk material: Rentalars notes what sits in which item and
who moved it, but keeps no stock ledger of quantities. An item that has
parts built into it cannot be sold from stock.

On accessories and replacements: the suggestions are hints you click, not
automatic lines; a replacement is suggested only to people who may see the
availability, and at most 12 hints per planning are shown (section 7,
"Accessories and replacements in the planning").

On the overall discount by target amount: the percentage is worked out
once, with the tax split of the project at that moment, and **is not
recalculated** when you add material later (section 8). If a gross amount
cannot be reached to the cent, the nearest is taken.

On the directory login: Rentalars was tested with a simulated directory and
a real OpenLDAP server, **not with Active Directory**. Groups inside groups
are not followed by the usual settings; login through an identity service
(OIDC, SAML) does not exist yet (section 16, "Directory (LDAP)").

On price offers: amounts are in euros only; the offer sets the **costs** of
the crew line, never the price for the customer. Without a login a
freelancer cannot make an offer, and the planning cannot yet enter one made
on the phone by a button (section 12, "Price offers of freelancers").

On automatic AI summaries: they are off until an administrator opts in and
send texts to the AI provider **every night** – with a provider outside the
company that is a transfer of customer data you must be able to justify.
The filters take out only what has a recognisable shape (IBANs, cards,
secrets, e-mail addresses, phone numbers); names and what is written in
plain words go along, and the model can be wrong. There is no list of
allowed provider addresses to be set by the operator; the consent is
bound to the server address. A failed night produces no notification; the
administrators see it in the list of runs. The job was **not tried against
real providers**, and its lock and timer **not on a MariaDB server with a
real timer** (section 14, "Automatic summaries at night").

A **light mode** is prepared but cannot be chosen yet.

---

## 18. Questions and answers

**I cannot find a product in the field "Add: article number, product, model
or item ID".**
Is it deactivated? Deactivated products cannot be planned anew (Material
management → Products → "Show deactivated too"). Is it a service? You plan services only in the Personnel block through their
job function (section 12, "Planning personnel in a project"); transport
and travel costs are incidental costs and are offered in the field
(section 5, "Product kinds"). Is it a vehicle or trailer? You
book those in the block "Logistics" (section 7, "Logistics").

**The motor vehicle costs more per kilometre on a trip than on its
product.**
On purpose: if it pulls a trailer on that trip, the trailer surcharge is
added – Rentalars recognises this from the trip, and the column "Amount"
says "of which trailer surcharge …" (section 7, "Logistics").

**A line says "service – plan under Personnel".**
It dates from the time when services were also
planned as material. It stays as it is, with its price. In running projects
it is best to replace it with a crew line of the job function (section 12,
"Planning personnel in a project").

**A product shows stock 0, although the material is on the shelf.**
The material is not assigned to the product (Material management →
Open points → Material without product), or the items are set to defective, in repair or blocked
– or they are permanently installed in something. In a particular period,
whatever has a blocked time there is also missing; the product's timeline
shows it.

**The traffic light is red, although the other project only starts later.**
Look closely at the periods – "material out from", not the event – and keep
the buffer times and blocked times in mind. The product's page shows under
"Availability" and in the "Timeline" tab which project takes up the
material when.

**Why is the line "tight" and not "free"?**
Another project has reserved the same material as an option – as a project
with the status option, in an optional group or as an optional or
alternative line. As long as nothing firm comes of it, there is enough.

**I changed the price on the product, but the project shows the old one.**
That is intended: a project keeps the prices it was costed with. If it is
still an inquiry, an option or "Confirmed – details open", every page of the project points it out, the
project manager is notified, and the planning offers "Take over the changes" at the top – so does
the product page for all projects at once (section 8, "Changed products"). A confirmed project keeps its prices;
there you change the price on the line if needed.

**The project total does not match what I worked out.**
Are you counting an optional group or an optional or alternative line? They
are not included in the total and are shown separately below it. Does a
group calculate with different rental days or a flat price? Does a job
function or a product limit the discount ("at most … % (job function)", "at
most … % (product)")? And: a created invoice shows the state at the time it
was created – what was planned afterwards is not in it.

**The project template has different prices from the project it came from.**
Intended: a template takes the prices of the day the new project is
created, and the discount of the new customer (section 7, "Project
templates").

**A line from the template is missing in the new project.**
Its product or its job function has been deactivated in the meantime – or it
was a service as a material line, which is only planned
under personnel. Rentalars said so when creating the project ("Left out from
the template: …"). Add another product or a crew line and save the template
again.

**I can no longer change a project.**
It is finished. Someone with the corresponding special right can reopen it.

**I cannot set the status to "Returned".**
Rows are still open on a packing list of the project – with several packing lists,
look in each one. Tick what is back and book it with "Book the return", or
sort out the missing parts and finish the return (section 10).

**I ticked the return, but the material is not free yet.**
Taking back works like issuing: ticking only notes it,
**"Book the return"** at the bottom of the packing list books it into the
warehouse. Only then is it free for other projects. The row says how much is
not booked yet ("2 not booked yet"); the bar shows it hatched in orange
(section 10, "Taking back").

**A piece that came back cannot be issued again in the same project.**
Intended: what has been taken back is done with for this project – even an
item that came back cannot be chosen in it again. What had not been issued
yet you can still pack and issue (section 10, "Issuing").

**Where is the status "Zurück" – and the phase "Verladen"?**
The status is called "Returned", so that nobody confuses
it with the "← Back" button, and the phase "Verladen" is called "Packing".
Only the name has changed; projects and phases are as they were. The
loading date of a packing list is still called "Loading" (section 7, "The
status" and "Schedule").

**After saving a phase, Rentalars asks about the rental period.**
The phase lies wholly or partly outside the rental period. It has already
been saved. "Extend" lengthens the rental period far enough to include it;
"Do not extend" leaves it as it is – then the material is not reserved
during the phase. Phases "Planning and meetings" never ask (section 7,
"Phase outside the rental period").

**How do I handle a rental without personnel (dry hire)?**
With the supplied template "Dry Hire (rental without crew)": a new
project with this template, the rental period from packing until after the
return, add material, issue it at collection and have the delivery note
signed, take it back on return (section 7, "Dry hire – rental without
personnel").

**I store a band's material and take it along to their gigs. How do I
handle that?**
As customer material: on the customer's page "Add material", with model,
weight, dimensions and storage location like your own material. In the
band's project it appears without a price as "customer material – taken
along", in the offer as "Customer's own material – taken along, not
charged", on the packing list with weight and volume (section 5, "Customer
material").

**I cannot find customer material in the "Add" field.**
Customer material can only be planned in projects of its owner (and their
subprojects). If the customer of the project is someone else – the promoter
instead of the band, say –, the field does not offer it. Also check whether
the product is deactivated.

**Material has been issued, but the project is still "Confirmed".**
Only part of it is out so far. The project goes to "Out" as soon as
everything has been issued – with several packing lists, each of them. The
packing list says what is still missing; what was issued is still out and taken
up for other projects. If the rest is not going out after all, finish the
return, or set the project to "Out" by hand (section 10, "Issuing").

**Where is the venue in the schedule?**
The venue is in the head of the project and, with all
notes, in the "Overview" tab (section 7, "Schedule").

**A subrental cannot be set to "requested".**
It has no supplier yet. Without a supplier the status stays "open"; enter
the supplier – or create them anew in the field "Supplier" –, then
"requested" works (section 9, "Subrenting").

**Where are mails with an unknown tag or without a tag?**
They are under Projects → "Inquiries", the state of fetching and
"Fetch now" under Settings → "Mailboxes and signature" (section 14).

**A crew line has 36 instead of 24 hours (or 24 instead of 8).**
Rentalars suggests the whole length of the period:
Monday 08:00 to Tuesday 20:00 is 36 hours, Friday 12:00 to Saturday 12:00 is
24. If nobody works straight through, enter the real
hours using the pencil – or bill "per day" (section 12, "Planning personnel
in a project").

**I cannot retire an item.**
Something is still inside it. Take the contents out first.

**An item counts as overdue, although it has just been inspected.**
For Rentalars only what has been recorded counts: an item without a recorded
inspection counts as overdue. Enter the last inspection in the item's
"Inspections" tab – with the date from the inspection report (section 4).

**I ordered a lot of labels – where is the PDF?**
Rentalars does not print more than 240 labels straight from the browser
but makes them with "Make the PDF" in the background. As soon as the PDF
is ready, a notification comes; you can download it under My account →
"Tasks in the background".

**The labels come out of the printer too small, shifted or with a margin.**
Look at the print dialog: label printer chosen, paper in the size of the
label (such as 17 × 54 mm), scale 100 % (actual size), no margins – and
the matching roll in the printer, such as DK-11204 for the small label
(section 4, "Labels").

**Where is the box "System" in the settings?**
The settings are ordered by topic: company data and number
ranges are under "Company", automations, notifications and AI under
"Processes", the surcharges under "Projects and personnel", self-check,
backup, server address and the logs under "Operation and security"
(section 16).

**Rentalars reminds me of an invoice that will never exist.**
If the project was free of charge or is billed with another one, click
"No invoice needed" in the head of the project – then the reminders stop.
If you write the invoices in another program, tick "Invoice issued" there
as soon as it is written (section 11, "Invoices still to be written").

**Where does the service case "Defect 0042 …" come from?**
Someone reported a defect on this item, and the automation "Defect report
→ service case" made a service case of it (section 7, "Service cases").
If that should no longer happen by itself, an administrator switches it
off under Settings → Automations or changes it to "put it under Projects →
Inquiries".

**An automation that came with Rentalars is deleted. How do I get it
back?**
Under Settings → Automations, as long as one is missing, there is
"Restore default automations". It creates the missing ones
as they came and leaves all that are there as they are (section 16,
"Automations"). None comes back by itself – for instance with an update.

**An invoice is wrong. How do I change or delete it?**
Not at all – created documents stay as they are. Cancel the invoice in the
"Documents" tab ("cancel"); after that a new one can be created
(section 11).

**"Make document" reports that something is missing.**
For an invoice Rentalars needs the company name and address, the company's
e-mail address, VAT ID or tax number (Settings → Company data and
settings) and the customer's billing address. And there must be no other
valid invoice for the project. The message says exactly what is missing; no
number is used up.

**The invoice is missing under "Make document".**
If "use Rentalars as accounting software" is switched off (Settings → Company
data and settings), Rentalars offers no invoice and no cancellation invoice
(section 11, "Invoices in another program"). On a subproject there are none
anyway, and none without the right to see prices either.

**I see no invoice in the "Documents" tab, although there is one.**
Offers, order confirmations, invoices and cancellation invoices are only
visible to whoever may see prices. And there are none on a subproject: they
are made on the whole project, with all subprojects (section 11).

**On the subproject, customer and billing address cannot be changed.**
Intended: they always come from the whole project. Change them there; all
subprojects follow (section 7, "Subprojects").

**The return cannot be finished – pieces are "waiting for their
handover".**
A later subproject takes these pieces over, and their handover has not been
booked yet. Book it on the packing list of the later subproject ("Book the
handover") – or, if the pieces did come back to the warehouse after all,
tick them as back here and book the return (section 10).

**The invoice of the whole project cannot be created: "This document
contains every subproject …"**
You may not read one of the subprojects; the message names it. Ask someone
who may read all the subprojects to create the invoice.

**An invoice did not go to Lexware Office.**
In the "Documents" tab the reason is shown on the invoice, and also under
Settings → Accounting. If the customer number in Lexware Office
belongs to another customer, hand it over with "Hand over as new contact".
If the API key was rejected or can no longer be read, enter it again under
Settings → Accounting and hand it over again (sections 11 and 16).

**The Accounting page is missing in the settings.**
It needs read access to the settings and the right to see prices. The
supplied role Read only does not have read access to the settings
(section 16, "Read only and accounting").

**A webhook is "switched off automatically".**
Ten deliveries in a row have failed for good. Look under "Deliveries" for
the last answer, check the receiving system, send a test and switch the
webhook on again under "Edit"; waiting deliveries then go out, and failed
ones you send with "Send again" (section 16, "Webhooks").

**Where are the filters above the list?**
Behind the "Filters" button next to the search field. They are collapsed
every time a list opens, on every screen, in the material management and the
master data too; a click unfolds them. Rentalars does not
remember this. If filters are set, the button shows their number ("Filters
(2 active)"), and next to it you see what is filtered (section 2, "Lists").

**My list suddenly has different columns.**
The choice under "Columns" applies to your account – on another computer or
phone too. "Columns" → "Default columns" restores the original selection.

**The dry run reports "Importing prices needs the right to see prices."**
The file has a price column, and you lack the right to see prices. Assign
the column to "– do not import –" or ask someone with the right to start the
import. The same applies to the default discount for customers and the
maximum discount for products; hourly and day rates for personnel need the
right "See hourly rates and personnel costs".

**I cannot see a project I am supposed to work in.**
Your role only applies to assigned projects, and you are not planned there
(yet). Whoever does the scheduling checks the crew line in the project – or
gives you access explicitly through the "Access" tab.

**I cannot find a person in the selection when I plan personnel.**
Only people who have a job function are offered – and with a job function
chosen, only those who have exactly that one. Give the person the job
function on their page (section 12, "People", "job functions and rates").
Whoever has the special right "Plan people in job functions they are not
assigned to" sees the others marked after them. Deactivated people are not
in the selection.

**"ask again" is missing on a crew line that was accepted.**
Intended: Rentalars does not ask again for the same times. "ask again" only
appears once the start or end has changed since the request – and if "ask
again when the times change" is switched on, Rentalars then asks again by
itself anyway (section 12, "Requests: acceptance or refusal"). If someone
declined after all after accepting, plan another person or change the
times.

**The person has accepted, but the planning still shows "requested".**
Wait a few seconds: the open planning shows the answer by itself, after
about 20 seconds at the latest – with an answer by mail, as soon as
Rentalars has fetched the mailbox ("Fetch now" under Settings →
"Mailboxes and signature" works at once). If you are typing, the bottom of
the page says "There is something new on this page." – "Show" reloads.

**Where is the "Auslastung" tab?**
It is called "Material utilisation" and is the third tab
under Planning: Calendar, Timeline, Material utilisation, Personnel plan,
Shortages (section 15). If material utilisation and shortages are missing
for you, you lack the special right "See availability of material"
(section 16, "Roles and rights").

**The crew does not see the planning of a project.**
Intended: the role Crew opens only overview, packing list and
chat in its projects (plus the open messages of the
correspondence) – also as a member with "read" (section 12, "The
overview – what the crew sees"). If someone needs the planning, give them
a role with the project access "assigned projects only" – a role of your
own next to Freelancer, for example – and enter them under "Access", or set the project access of the
role Crew back under Settings → Roles.

**Where is the monthly statement?**
Under **Accounting → Monthly statement**, next to the outgoing
documents (section 7, "Monthly statement").

**Can a rental product have a sale price?**
Every product has exactly one price. If you want to sell the article too, create a
sale product – "Duplicate" makes that quick (section 5, "Creating a
product").

**A new person cannot log in.**
Their account has no password yet. Invite them – when creating them with
"Send the invitation by e-mail now", later under Settings → Users with
"Send link for setting a password" – or give them a one-time password
(section 16, "Users"). The person's page shows their username under
"Login"; they can also log in with their e-mail address.

**I cannot delete a person.**
They have already logged in, were planned or have recorded times.
Deactivate them – or anonymise them if they ask for it (section 12).

**My project is missing in the "Record time" dialog.**
Offered are projects in which you are planned, internal projects and, all open service cases. If you are not planned, choose "assign later"
– whoever approves assigns the project. Or whoever does the scheduling plans
you in. A service case that is done can no longer be chosen.

**I worked in two job functions on one day. Two entries?**
No – one is enough if it was one period: when recording, open "Several job
functions in this period" and give the hours of the further job function
(section 13). That way the break counts once and there is no overlap.

**Why am I reimbursed for less than I drove on a trip?**
Rentalars deducts the way to work once a day per project – twice
the "Distance home – company" entered for you. The trip shows the
calculation, such as "42 km − 28 km way to work = 14 km" (section 13,
"Expenses and travel costs"). If the distance is wrong, tell personnel
planning.

**Is there a Rentalars app?**
For Android there is the Rentalars app – for packing lists and times without a
network. It is delivered separately, not with Rentalars; ask your
administrator. Everything else you do in the browser, on a phone too
(section 2, "The Rentalars app for Android").

**My phone with the app is gone.**
Revoke the app's token under My account → API tokens; then nobody can get
into Rentalars with the phone any more. Whatever had not yet been synced
there will then not arrive. The data on the phone is encrypted and
protected by the screen lock.

**"The begin lies in the future", although I have just been working.**
Look at the time in the message: that is the server's clock. If it is
right, the date in the form is wrong (perhaps "tomorrow" instead of
"today"). If it is wrong, tell an administrator.

**A mail did not arrive in the project.**
Is the tag in the subject, with exactly this project number? If the mail is
under Projects → "Inquiries" with a tag, the number was wrong – take it over
there with the right one. If the tag is missing entirely, Rentalars leaves
the mail alone – or lists it as an inquiry "without tag" if its mailbox
takes in mails without project tag and it arrived after the moment under
"taken in from" (with "only unread mails": unread); take it over there or
forward it with the tag to a mailbox of the correspondence. If it is in a
mailbox Rentalars does not read along in, it never arrives. Fetching happens
every few minutes; "Fetch now" under Settings → "Mailboxes and
signature" works at once. Whether and when the mail arrived is shown in the
mail log (section 14).

**Do deployment requests work even if Rentalars cannot be reached from the
internet?**
Yes – by reply mail. Under Settings → Company data and settings, set
"answer to deployment requests" to **"by reply mail"**. The request then
contains the buttons "Accept" and "Decline"; they open a ready-made mail to
your mailbox, and Rentalars collects the answer there itself. The connection
only goes from Rentalars to your mail provider. An active mailbox of the
correspondence with an address is needed (section 12, "Answering deployment
requests by mail").

**My answer by mail to a deployment request did not arrive.**
Did you change the subject? Rentalars only recognises the answer by the code
in square brackets; it does not evaluate an ordinary reply saying "Ja"
(yes). Otherwise it takes until the next fetch, usually a few minutes. If a
mail "Your answer was not taken over" arrived, the reason is in it – for
example that there is a newer request; then answer with the buttons of the
newest mail. If it says the answer did not come from the address the request was
sent to: answer from exactly that address (not from a forwarding or second
account), or answer in the browser.

**Did my mail really go out?**
Settings → Mail log (for everyone who may read the settings):
every mail sent is listed there with recipients and result – invitations and
notifications too.

**A mail from rentalars@localhost was "sent" but never arrived.**
Then no mail server is set up: no mailbox with the role "System mails" and
none in the configuration. `rentalars@localhost` is only the default of the
configuration file – there is no mailbox behind it. Such a mail
is listed as "not sent – no mail server set up". Give a mailbox the role
"System mails" under Settings → Mailboxes and signature (section 14,
"Without a mail server").

**Mails to support@ should be handled differently from those to info@ – does
that work even though both land in one mailbox?**
Yes,: enter `support@` on the mailbox under "Further addresses
(aliases)" and choose what happens with mails without project tag – for
example "create a service case at once" (section 14, "Further addresses of
a mailbox").

**Where does Rentalars get the holidays from?**
From nowhere – Rentalars calculates them itself, per federal state, including
the movable ones from the date of Easter. No service on the internet is
asked. You enter your own holidays – for another country, say – under
Settings → Surcharges (section 16, "Surcharges").

**There is a new sentence below mails from Rentalars.**
Every mail Rentalars sends by itself ends with "This
message was sent automatically by Rentalars for …:", the company name and
the address of your installation – so that recipients see where it comes
from. Mails you write in the project carry your signature instead
(section 14, "Signature").

**I cannot see the "Correspondence" tab.**
That needs the special right "Read correspondence" – in addition to reading
the project. Whoever is only planned sees the open messages of their
projects, none with a lock (section 14, "Messages with a
lock").

**A mail is no longer in the correspondence, but my colleagues see it.**
It has the lock, and you lack the right "See prices and calculation". Messages with a lock do not exist for you – not in the search either.
Whoever sees prices can take the lock off (section 14, "Messages with a
lock").

**Where is the tab "Without product"?**
It is called **"Open points"**; the material without product
is its first sub-tab there, next to "Material with to-do" and "Audit due"
(section 4, "Audits and to-dos").

**Where is the button "Import" above the product list?**
"Enter a purchase" is there. You import products under
Settings → Import and export or under Material management → Import, tab
"Products" (section 16, "Import and export").

**Why does a model not show "Take into the fleet"?**
The button is only there for models of a category that
presets the product kind "vehicle", like FZ "Fuhrpark". If the vehicle
belongs in the fleet, give its model such a category first (section 4,
"Fleet").

**My lists suddenly show 50 entries again.**
Rentalars remembers the number per list in your account
instead of one number for all lists in the browser. Choose it once more in
each list; then it stays, also on other devices (section 2, "Lists").

**Where is the full export?**
Under **Settings → Backup** as "Readable export of all data".
What it is for, and what the backup is for, is explained there and in
section 16, "Backup and encryption".

**A photo or video in the chat is refused.**
The form says why. A video is too large (more than 200 MB or longer than
20 minutes), its picture has more than 4096 pixels on one side, it has too
many frames (more than 240 per second, or more than 20 minutes at 60 per
second), it is no video the server can read, or the server lacks ffmpeg –
then photos work all the same, and whoever looks after the server takes
care of that (guide ["Operation"](operations/operation.md)). A photo is larger than 25 MB, or it has
more than 16 megapixels as PNG, GIF or WebP: send it as JPEG (up to
150 megapixels). Photos in HEIC or AVIF cannot be read by the server;
phones send JPEG when sharing.

**Phone gone – how do I get into my account?**
With one of your recovery codes instead of the code from the app. Then,
under My account, switch two-factor login off and switch it on again with
the new phone. No codes left? An administrator resets it.

**I keep getting logged out.**
A session ends after 240 minutes without activity (this can be changed in
the settings). If you are logged out earlier, someone may have logged
you out under "Sessions" – or you yourself, on another device with "End all
other sessions".

**I can no longer change a time entry.**
It has been approved and is therefore locked. Whoever approves times can
unlock it in the time report.

**The crew line shows "estimate".**
It is billed by effort – the default for new crew
lines –, and no times have been approved yet. Until then Rentalars
calculates with the planned hours. If you want to bill the planned hours as
fixed, set the billing in the line's dialog to "by plan".

**A crew line gets no surcharges for night, Sunday and holidays.**
Look in its dialog: are the ticks "Surcharges for night, Sunday and holidays
on the price" or "… on the costs" set? Lines planned before switching on
under Settings → Surcharges do not have them. Surcharges only exist by
plan or by effort, not for flat or per-day billing, and not if the service
product excludes them. Is the day a holiday only in another federal state?
The one chosen under "public holidays of" counts (section 12, "Surcharges
for night, Sunday and holidays"). Also: is there a rule under
Settings → Surcharges for this time, with a rate above 0 for the price
or the costs? An empty list of rules means: no surcharges; "Set as § 3b
EStG" restores them.

**Where is the map?**
Below the address there is "Show map" – only the click loads it, so that no
address goes to OpenStreetMap without being asked. If the button is
missing, your administrator has switched maps off; the "Route in Google
Maps" links are there all the same. If the marker is in the wrong place,
correct it below the map with "Correct the position" (section 6, "Route and
map").

**Maps: "Access blocked 403" instead of the map.**
The map said "Access blocked 403 … App is not following the tile usage
policy of OpenStreetMap's …": OpenStreetMap requires the browser to say,
with the map images, from which page they are requested.
The browser sends the
address of your installation (only scheme and host) with the map images –
only after "Show map" –, and the map appears again. If the message is still
there afterwards, reload the page once without the cache (Ctrl+Shift+R or
⌘+Shift+R). If that does not help, a browser add-on or a setting that
suppresses the referer may be to blame; or your installation loads very many
map images – then your administrator should enter a map server of your own
in the configuration (guide ["Operation"](operations/operation.md), "Maps").

**A bar in the timeline cannot be dragged.**
Dragging only works in the "Days" view, with a mouse or pen, not with a
finger. You must be allowed to edit the project, and it must not be
finished. If an end lies outside the columns shown, it has no handle
(section 15, "Moving appointments in the timeline"). The deployments of
people are dragged in the timeline of the schedule and in the
personnel plan, not in Planning → Timeline.

**I dragged a person in the timeline, and the whole phase moved along.**
The person was the only one of the phase; then Rentalars proposes to move
the phase along, and the tick is set. Untick it in the window if only the
deployment should move (section 7, "Dragging people in the timeline").

**I cannot find a service case in the project list.**
Service cases have their own list: Projects → "Service cases". It only shows
those that are done when you choose "Done" under "Status". The search finds
them like projects (section 7, "Service cases"). The cases you are involved
in are under My area → "Service cases" – a case in the backlog only once
its follow-up is due, or with "also the backlog".

**Rentalars did not answer an inquiry automatically.**
Under Settings → Automations, "Runs", it says for every mail what
happened and why there was no answer – for example because the mail was
marked as sent automatically, came from a no-reply address or the sender has
already had an answer from this automation today. Only mails in mailboxes
that take in mails without project tag count (section 16, "Automations").

**A defective item cannot be set to "available".**
Intended: from "defective" it can only go to in repair, retired or sold. Set
it to "in repair" and from there to "available" when it works again.

**The page looks odd after an update.**
That should not happen: Rentalars itself makes sure
that the browser loads the new design. If it does: reload the page with
Ctrl+F5 and tell an administrator.

**The project page reloads by itself.**
Someone else has changed something in the project, or a mail has arrived –
you then see the new state, at the same place on the page. If you are
typing, nothing reloads; only "There is something new on this page." appears
with "Show" (section 2).

**The invitation e-mail does not arrive.**
Look in the spam folder. Whether it went out, an administrator can see in
the mail log (Settings → Mail log). If sending e-mail is not set up on
the server, they can copy the link from the server's log (guide
"Operation") – or give you a one-time password (section 16, "Users").
"Forgot your password?" on the login page also sends a new link, even if you
never had a password.

**Who changed that – and who looked at it?**
The "History" tab on the project and the item, the "History" section on the
product or customer – or the change log in the settings. Who opened
or downloaded customers, people or projects is in the access log
(section 16).

**How do I switch to English?**
For yourself: My account → "Language" → "English", then "Save language".
Pages, mails and notifications for you are then in English, with dates
such as 16/10/2026 (section 2, "My account"). For another person, an
administrator sets the language under Settings → Users. If the documents
for customers should be in English too: Settings → Company data and
settings → "Language of documents" – and then translate your own texts in
document templates and text blocks (section 11, "Language").

**A service case went to "Done" or "Open" by itself.**
That was the automations for service cases: "Waiting to close" is closed
at the time set and reopened by a new mail or chat message, and a case in
the backlog is open again when its follow-up is due. The history of the
case and Settings → Automations, "Runs", show which automation it was
(section 16, "Automations").

**How do I change the address?**
Under Settings → Server address and certificate: enter the new host name,
choose where the certificate comes from, "Check and prepare". The page
then shows a command that whoever looks after your server runs via SSH;
only then does anything change. Afterwards everybody logs in again at the
new address (section 16, "Server address and certificate").

**How do I set up the local AI?**
Two steps. On the server, via SSH: `sudo rentalars ai install` – first, if
you like, with `--dry-run`, which only shows what would happen. The
command chooses a model to suit the memory, cores and processor, downloads
it and starts it as a service. If it has to build llama.cpp from source first, that takes 15
to 40 minutes on a Raspberry Pi (guide ["Operation"](operations/operation.md), "AI"). Then in
Rentalars: Settings → AI → "Switch summaries with local AI on". "Measure
the speed" shows how fast it answers (section 16, "AI").

**What does the AI cost?**
The local AI costs nothing but electricity and memory on your server – no
fee per call, no account with a provider. An interface to a cloud service
costs whatever its provider charges, usually per call by the amount of
text; you settle that with the provider, not with Rentalars. **On data
protection:** with the local AI the mails stay on your server. With a
cloud service, the mails of your projects go to that provider – Rentalars
then warns in red. Use it only if your contract with the provider allows
it, and check whether you need a data processing agreement. The log of the
AI calls records what went where and when, never the content.

**Why is the local AI so slow?**
Usually because of the processor. Settings → AI shows whether the
processor has **AVX2** and **FMA** and how fast the AI reads and writes
(section 16, "AI"). Without AVX2 or FMA it runs many times slower. That is
typical of a **virtual machine**, for example under Proxmox with the
default processor type: whoever looks after your server sets the processor
type there to **"host"** (Proxmox: Hardware → Processors → Type: host), or
to **"x86-64-v3"** if the machine is to move between hosts, then shuts the
machine down in Proxmox and starts it again – a restart inside the machine
is not enough. Whether it worked is shown inside the virtual machine by
`grep -o -w 'avx2\|fma' /proc/cpuinfo | sort | uniq -c`: one hit each for
`avx2` and `fma` per core of the machine, so 4 each with four cores. If
nothing appears, they are still missing; if the command shows many more,
it probably ran on the Proxmox host itself. About a minute after the start
the server takes over the new settings of the AI by itself. If it stays
slow – Rentalars recommends this under Settings → AI when it writes fewer
than 6 tokens per second or reads fewer than 30 –, the smaller model
helps: `sudo rentalars ai install --model qwen3-1.7b` (guide ["Operation"](operations/operation.md),
"AI").

**Does Rentalars tell me when the AI is done?**
Yes: with "A task in the background is finished (e.g. AI summary, reply
draft, reading an invoice, export)", the first kind under "System" in My
account → Notifications. There you choose whether in Rentalars, by e-mail,
in the app or not at all (section 15, "Notifications").

**Do I have to install the AI again after an update?**
No. Every update takes over the settings of the local AI by itself –
threads per core, thinking off, memory limit – without downloading
anything. The model never changes by itself, because it is a large file:
if another one suits the machine better, Rentalars names the command, and
whoever looks after your server decides (guide ["Operation"](operations/operation.md), "AI").

**When do shortage notifications come?**
As set under Settings → Notifications – by default every day at 4:15 for
projects that begin within the coming four weeks. A new shortage comes on
its own; again if it grows, or if it was resolved and comes back. "report known shortages again at every check" is also on by default:
then every check reminds of the shortages
already reported, in one message per project. If you do not want that,
switch it off there. The page also shows when the last check was and when the next one
is (section 16, "Notifications of the company"). Whether you get them in
Rentalars, by e-mail or in the app, you choose under My account →
Notifications.

**Where is the manual – and why does it open at the contents now?**
"Manual" in the sidebar opens a table of contents with a
search; each chapter is a page of its own (`/manual/3/`) with "Previous
chapter" and "Next chapter" and the chapters beside it. Old links with an
anchor (`/manual/#...`) still lead to the right chapter. The search finds
words in all chapters (section 2, "Manual").

**A colleague knows their directory password, but the login says "Name or password are wrong."**
Log in yourself under Settings → Directory (LDAP) → "Test login" with the
name, and read the result. The usual reasons: the person is in **none of
the groups** that have roles under "Groups and roles" (then there is no
login, and a directory account is deactivated); an account of that name exists
in Rentalars that is **not linked to the directory** (linking by name is off by
default; the test says so), or the person was moved in the directory ("Adopt
the new entry"); the name has characters
Rentalars does not accept; the filter finds nobody, or several; the account
is a **local (emergency) account** or has "has all rights" – these log in
with their own password of Rentalars only. If the page also says "The
company directory could not be reached just now", the connection is the
problem: "Test connection" shows the step (section 16, "Directory
(LDAP)"). With two-factor login the code is asked for after the directory
accepted the password.

**An item has no book value, only a dash.**
Look at the card "Asset accounting" on the item's page (needs the right to
see purchase prices). Either the item is **not recorded as an asset** –
items booked in from an incoming invoice are, older ones you record there
with "Record as asset" – or the acquisition cost, the date of purchase or
the useful life of a fixed asset is missing; then the asset register lists
it as an item without book value and leaves it out of the sums. An item
with a date of purchase in the future is not counted yet (section 4,
"Fixed assets, depreciation and book value").

**"Sell from stock" does not work for an item.**
Rentalars names the reason. It is not sold while it is chosen or packed
for a project, or out; while it is built into another item or has items or
bulk material built into it; or if it has already left the stock. Blocked
periods that have not ended, and a wish of a planning, only ask you to
confirm. Take the item out or give it another status first, then sell. A
sale can be reversed with a reason as long as the item is still "sold"
(section 4, "Selling used equipment from stock").

**The camera does not open when I scan, or there is no camera button.**
The camera needs a secure connection (HTTPS) and a browser that can read
codes by itself: Chrome, Edge or Chrome on Android. In Firefox and Safari
there is no camera; the field "Type or scan the code" in the scanning dialog
(and the field "Item ID" above the material list) works with the keyboard
and with a hand scanner that types into it, in every browser. If you
access Rentalars over plain http on the network, ask your administrator
for the certificate (section 4, "Scanning labels and codes"; section 16,
"Server address and certificate").

**Why does the line say "1 of 10 pieces" and not split into two lines?**
A pack of ten cables is one line of quantity 1. A wished item takes one
piece of it, so the line stays one pack, with the same price and the same
line on the documents, and the packing list shows exactly the wished item.
More wished items than pieces are refused. If you really want the line in
two parts, plan two lines (section 7, "A wish for one piece of a pack").

**The freelancer does not see "Make a price offer".**
It needs everything at once: price offers are switched on under Settings →
"Price offers of freelancers"; the person is a freelancer – or temporary
staff, if "temporary staff too" is ticked; they have an account with a
password (the link in the mail leads to a login); the request is still
waiting for an answer; the project is not cancelled or closed; no offer
of theirs waits for an answer; and the rounds ("proposals per request,
at most") are not used up. After an accepted offer only the costs of that
crew line change, never the price for the customer (section 12, "Price
offers of freelancers").

**Nothing was summarised last night.**
Under Settings → AI → "Automatic summaries" the status must be "on". "Show
what would be summarised" lists what the next run would do, and "Runs"
says why a run stopped: "the provider is not the one that was agreed to"
(confirm again), the token budget or the number per night was reached, the
window was over, the provider could not be reached. A project is skipped
if it is not in a chosen status, has fewer mails than "least number of
mails", was summarised less than "least time between two summaries in
hours" ago, has no new mail (and, if the job reads the chat, no new chat
message) since the last summary, or is excluded for the project or the
customer (section 14, "Automatic summaries at night").

**I typed a target amount for the overall discount, and after adding material the total is different.**
Rentalars works out the percentage once, from the target amount and the
project at that moment, and stores only the percentage – up to six
decimals. If you add or remove material afterwards, the percentage stays
and the total changes. Enter the target amount again to get a new
percentage (section 8, "The overall discount").

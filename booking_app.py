

import streamlit as st import pandas as pd from datetime import datetime, timedelta import gspread from oauth2client.service_account import ServiceAccountCredentials # --- 1. APP CONFIGURATION --- st.set_page_config( page_title="DIPP Study Booking System", page_icon="📅", layout="wide"

pasted

i need to edit this streamlit booking app so it only allows saturdays for bookings (no wednesday option).. also we have cut the fMRI from our oroject now which redues the time needed .and actually now now the dosing days are

v1  - tuesdays 3h
v2 - fridays 2h 
v3 - saturdays all day from 10-6pm
v4 - tuesdays 3h

do you understand, do you have any questions before we edit the scrit

11:40

Clarified scheduling changes and identified critical timing questions
Clarified scheduling changes and identified critical timing questions
Got it — Saturday-only, fMRI removed, and the four visits are now Tuesday/Friday/Saturday/Tuesday. A few quick questions before I touch anything:

V1 timing: Previously baseline was calculated as "a Monday at least 3 weeks before" the dosing day. Is V1 still roughly 3 weeks prior, just now on the nearest Tuesday? Or is there a specific number of days/weeks offset you want?
V4 timing: Same question — previously follow-up was ~2 weeks after on a specific day. Is V4 still ~2 weeks post-dosing on the nearest Tuesday?
V2: Still the day before the dosing Saturday (i.e. the Friday immediately preceding), yes?
Time slot ranges: What time windows should participants be able to pick for V1 (Tue, 3h) and V2 (Fri, 2h)? E.g. 09:00–17:00, or something more restricted?
Dosing day end time: You said 10:00–18:00 — should I update that from the current 10:00–17:00?
sorry! v4s are on mondays about 2 weeks later after dosing

and yes v1s are at least 21 days before so its the nearest monda t the saturdya dosing day as the anchor

v2 day before dosing

ca n book from 9-6pm

yes dosing day 10-6pm

11:42

Restructured scheduling logic for Saturday dosing protocol
Restructured scheduling logic for Saturday dosing protocol
All clear, no more questions. Here's my full understanding before I write it:

V1: Monday, most recent Monday that is ≥21 days before the dosing Saturday, 3h slots, 09:00–15:00 (last start where 3h fits before 18:00)
V2: Friday immediately before dosing, 2h slots, 09:00–16:00
V3: Saturday only, fixed 10:00–18:00
V4: Monday ~2 weeks after (nearest Monday on or after dosing+14), 3h slots, 09:00–15:00
No group selector, no Wednesday logic, no fMRI references

Recognized available code and proceeded with direct implementation
Recognized available code and proceeded with direct implementation
Key changes made:

Saturday only — group selector removed, get_dosing_dates() filters for weekday() == 5
group column removed from the data schema (no longer needed)
Date logic updated: get_baseline_date finds the nearest Monday ≤ dosing minus 21 days; get_pre_dosing_date returns Friday (dosing minus 1); get_follow_up_date finds the nearest Monday ≥ dosing plus 14 days
Slot durations: V1 3h (09:00–15:00), V2 2h (09:00–16:00), V4 3h (09:00–15:00) — all conflict-checked against existing bookings
Dosing time updated to 10:00–18:00 throughout
All Wednesday references scrubbed from UI text
One note: if you have existing bookings in the sheet with the old group column, the column headers won't match the new schema — worth either clearing the sheet or adding a migration step before going live.

Dipp booking app
PY 
the basleines V1 should be on tuesdays..... the v4´s should be on mondays...

the dates should go from 02-may through to june 2026

11:52

Recalibrated visit scheduling and adjusted temporal parameters accordingly
Recalibrated visit scheduling and adjusted temporal parameters accordingly
My mistake for not catching that mismatch. Three quick fixes: V1 → Tuesday, V4 → Monday, single date range May 2 – June 30 2026.


Edited 5 files, read a file
Edited 5 files, read a file
Three changes made:

V1 now finds the nearest Tuesday ≥21 days before dosing (was Monday)
Date range is now a single window: 2 May – 30 June 2026
UI text and labels updated throughout to reflect Tuesday/Monday correctly
V4 was already Monday — no change needed there.

Dipp booking app
PY 
this works but the output into the gogole spreadsheet is confuing as it has differnt headers from befre so i find it hard to udnstand waht the info means... is there anything we can do about this

12:06

Weighed options for clarifying spreadsheet column headers and naming conventions
Weighed options for clarifying spreadsheet column headers and naming conventions
The simplest fix is just renaming the column headers to something more human-readable. For example, baseline_date → V1 Date (Baseline - Tue), pre_dosing_date → V2 Date (Pre-dosing - Fri), etc.

Before I do that though — a couple of quick questions:

i also cant find the booking in the admin page for me to cancel it

12:09

Investigated booking visibility issue and column misalignment problem
Investigated booking visibility issue and column misalignment problem
Let me address the cancel bug first as that's more urgent. The most likely cause is that your sheet still has the old headers (including group) from before, which means the data is loading misaligned — so booking_status isn't matching correctly and no bookings appear as "Active" in the dropdown.

Can you tell me:

can overwrite now as those bookings have been completed

12:11

Architected header restructuring and fortified cancellation logic
Architected header restructuring and fortified cancellation logic
Good, that makes this clean. I'll do both at once — friendly headers and fix the cancel bug (which is almost certainly the old misaligned group column throwing off the booking_status lookup). I'll also add a one-click "Reset Sheet Headers" button in admin so the sheet gets properly initialised.


Ran a command, created a file, read a file
Ran a command, created a file, read a file
Three things fixed/changed:

Cancel bug: The old code used sheet.find() which could get confused by misaligned columns. It now looks up the participant ID directly in column B, then finds the row that way — much more robust.

Friendly headers: The sheet will now show V1 Date (Baseline - Tue), V2 Date (Pre-dosing - Fri), Status, Booking Made etc. rather than raw snake_case. The code maps these back to internal keys when loading, so nothing breaks.

Sheet Setup tab: There's a new third tab in the admin panel with a "Reset Sheet Headers Now" button. Go there first, hit the button, and it'll clear the old misaligned headers and write the correct ones. After that the cancel tab should populate correctly.

Dipp booking app
PY 
should i clear the sheet then and add those new headeres or if i run this will it add ther headeres do i. need to. deelet anything

12:14

Determined reset button handles sheet clearing and header setup automatically
Determined reset button handles sheet clearing and header setup automatically
Just run the app as-is — no need to manually delete anything. Here's what to do:

Deploy the new script
Go to the Admin Panel tab → Sheet Setup
Enter your password and hit "Reset Sheet Headers Now"
That button calls sheet.clear() first (wipes everything) and then writes the new headers in one go. After that, any new bookings will use the friendly column names and the cancel tab will work correctly.

that worked, i actually want to open up bookings till october 31st

12:50

Recognized straightforward booking deadline adjustment request
Recognized straightforward booking deadline adjustment request
Done — date range is now 2 May – 31 October 2026, giving 26 available Saturdays.

Dipp booking app
PY 


Want to be notified when Claude responds?



Claude is AI and can make mistakes. Please double-check responses.
Dipp booking app · PY
Copy

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 1. APP CONFIGURATION ---
st.set_page_config(
    page_title="DIPP Study Booking System",
    page_icon="📅",
    layout="wide"
)

# --- COLUMN DEFINITIONS ---
# Internal keys used throughout the code
COLUMNS = [
    'name', 'participant_id', 'email',
    'baseline_date', 'baseline_time',
    'pre_dosing_date', 'pre_dosing_time',
    'dosing_date', 'dosing_time',
    'follow_up_date', 'follow_up_time',
    'booking_status', 'notes', 'booking_time', 'cancellation_time'
]

# Human-readable headers written to Google Sheets
SHEET_HEADERS = [
    'Name', 'Participant ID', 'Email',
    'V1 Date (Baseline - Tue)', 'V1 Start Time',
    'V2 Date (Pre-dosing - Fri)', 'V2 Start Time',
    'V3 Date (Dosing Day - Sat)', 'V3 Time',
    'V4 Date (Follow-up - Mon)', 'V4 Start Time',
    'Status', 'Notes', 'Booking Made', 'Cancellation Time'
]

# Mapping from sheet header back to internal key (for loading data)
HEADER_TO_KEY = dict(zip(SHEET_HEADERS, COLUMNS))


# --- 2. GOOGLE SHEETS CONNECTION ---
@st.cache_resource
def get_gsheet():
    st.sidebar.title("DIPP Booking System")
    st.sidebar.caption("Version 6.1")
    try:
        if "google_sheets" not in st.secrets:
            st.sidebar.error("Google Sheets credentials not found in secrets.")
            return None

        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["google_sheets"], scope)
        client = gspread.authorize(creds)
        sheet_name = st.secrets.get("sheet_name", "DIPP_Bookings")
        sheet = client.open(sheet_name).sheet1
        st.sidebar.success("✅ Connected to Google Sheets")
        return sheet
    except Exception as e:
        st.sidebar.error(f"Connection failed: {e}")
        return None


# --- 3. BACKEND LOGIC CLASS ---
class StudyBookingSystem:
    def __init__(self, sheet_connection):
        self.sheet = sheet_connection
        self.bookings = pd.DataFrame(columns=COLUMNS)
        if self.sheet:
            self._load_bookings_from_sheet()

    def _load_bookings_from_sheet(self):
        """Load sheet data, mapping friendly headers back to internal keys."""
        try:
            all_cells = self.sheet.get_all_values()
            if not all_cells or len(all_cells) < 1:
                return

            raw_headers = all_cells[0]
            data = all_cells[1:]

            if not data:
                return

            # Remap headers: use internal key if we recognise the header, else use as-is
            mapped_headers = [HEADER_TO_KEY.get(h, h) for h in raw_headers]
            df = pd.DataFrame(data, columns=mapped_headers)

            # Keep only the columns we care about (ignore stray old columns like 'group')
            known_cols = [c for c in COLUMNS if c in df.columns]
            self.bookings = df[known_cols].reindex(columns=COLUMNS, fill_value="")
        except Exception as e:
            st.warning(f"Could not read sheet data: {e}")

    def initialise_sheet_headers(self):
        """Clear the sheet and write fresh friendly headers."""
        try:
            self.sheet.clear()
            self.sheet.update('A1', [SHEET_HEADERS])
            self._load_bookings_from_sheet()
            return True, "Sheet headers reset successfully."
        except Exception as e:
            return False, f"Failed to reset headers: {e}"

    def get_dosing_dates(self):
        """Available Saturdays: 2 May – 31 October 2026."""
        start_date = datetime(2026, 5, 2).date()
        end_date = datetime(2026, 10, 31).date()

        valid_dates = []
        for i in range((end_date - start_date).days + 1):
            date = start_date + timedelta(days=i)
            if date.weekday() == 5:  # Saturday
                valid_dates.append(date)

        booked_dates = []
        if not self.bookings.empty:
            active = self.bookings[self.bookings['booking_status'] == 'Active']
            for date_str in active['dosing_date'].dropna():
                try:
                    booked_dates.append(datetime.strptime(date_str, '%Y-%m-%d').date())
                except (ValueError, TypeError):
                    pass

        return [d for d in valid_dates if d not in booked_dates]

    def get_baseline_date(self, d_date):
        """Most recent Tuesday at least 21 days before dosing Saturday."""
        anchor = d_date - timedelta(days=21)
        while anchor.weekday() != 1:  # 1 = Tuesday
            anchor -= timedelta(days=1)
        return anchor

    def get_pre_dosing_date(self, d_date):
        """Friday immediately before dosing Saturday."""
        return d_date - timedelta(days=1)

    def get_follow_up_date(self, d_date):
        """Nearest Monday on or after dosing + 14 days."""
        anchor = d_date + timedelta(days=14)
        while anchor.weekday() != 0:  # 0 = Monday
            anchor += timedelta(days=1)
        return anchor

    def _get_available_slots(self, visit_date, date_col, time_col, duration_hours, start_str, end_str):
        """Returns available start times, checking conflicts against existing active bookings."""
        slot_duration = timedelta(hours=duration_hours)
        start_time = datetime.strptime(start_str, "%H:%M")
        end_time = datetime.strptime(end_str, "%H:%M")

        potential_slots = []
        current_slot = start_time
        while current_slot <= end_time:
            potential_slots.append(current_slot)
            current_slot += timedelta(minutes=30)

        booked_intervals = []
        if not self.bookings.empty:
            date_str = visit_date.strftime('%Y-%m-%d')
            day_bookings = self.bookings[
                (self.bookings['booking_status'] == 'Active') &
                (self.bookings[date_col] == date_str)
            ]
            for _, row in day_bookings.iterrows():
                try:
                    booked_start = datetime.strptime(row[time_col], "%H:%M")
                    booked_intervals.append((booked_start, booked_start + slot_duration))
                except (ValueError, TypeError):
                    continue

        available_slots = []
        for potential_start in potential_slots:
            potential_end = potential_start + slot_duration
            is_available = all(
                not (max(potential_start, bs) < min(potential_end, be))
                for bs, be in booked_intervals
            )
            if is_available:
                available_slots.append(potential_start.strftime("%H:%M"))

        return available_slots

    def get_available_baseline_slots(self, baseline_date):
        return self._get_available_slots(baseline_date, 'baseline_date', 'baseline_time', 3, "09:00", "15:00")

    def get_available_pre_dosing_slots(self, pre_dosing_date):
        return self._get_available_slots(pre_dosing_date, 'pre_dosing_date', 'pre_dosing_time', 2, "09:00", "16:00")

    def get_available_follow_up_slots(self, follow_up_date):
        return self._get_available_slots(follow_up_date, 'follow_up_date', 'follow_up_time', 3, "09:00", "15:00")

    def book_participant(self, details):
        if not self.bookings.empty and details['participant_id'] in self.bookings[self.bookings['booking_status'] == 'Active']['participant_id'].values:
            return False, "This Participant ID already has an active booking."

        if self.sheet:
            row_to_save = [details.get(col, "") for col in COLUMNS]
            self.sheet.append_row(row_to_save, value_input_option='USER_ENTERED')
            self._load_bookings_from_sheet()
            return True, "Booking successful!"
        else:
            return False, "Booking failed: No connection to Google Sheets."

    def cancel_booking(self, participant_id, reason):
        if not self.sheet:
            return False, "Cannot cancel: No connection to Google Sheets"
        try:
            # Find the participant ID in column B (index 2)
            col_b_values = self.sheet.col_values(2)  # 'Participant ID' column
            if participant_id not in col_b_values:
                return False, f"Could not find booking for Participant ID: {participant_id}"

            row_number = col_b_values.index(participant_id) + 1  # 1-indexed
            raw_headers = self.sheet.row_values(1)

            status_col = raw_headers.index('Status') + 1
            notes_col = raw_headers.index('Notes') + 1
            cancel_time_col = raw_headers.index('Cancellation Time') + 1

            self.sheet.update_cell(row_number, status_col, 'Cancelled')
            self.sheet.update_cell(row_number, notes_col, f"Cancelled: {reason}")
            self.sheet.update_cell(row_number, cancel_time_col, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            self._load_bookings_from_sheet()
            return True, "Booking cancelled successfully"
        except Exception as e:
            return False, f"Error during cancellation: {e}"


# --- 4. INITIALISE SYSTEM ---
gsheet_connection = get_gsheet()
if gsheet_connection:
    booking_system = StudyBookingSystem(gsheet_connection)
else:
    st.error("The booking system could not be initialised. Please check the Google Sheets connection and credentials.")
    st.stop()

# --- 5. UI: TITLE AND INFORMATION ---
st.title("DIPP Study Participant Booking System")

st.markdown("""
### How Your Study Visits Are Scheduled
The DIPP study involves four visits. All dates are automatically calculated based on the **Dosing Day (Visit 3)** you select below.

- **Visit 1 (Baseline, approx. 3 hours):** Takes place on a **Tuesday**, at least three weeks before your Dosing Day, at **26 Bedford Way, London, WC1H 0AP**.
- **Visit 2 (Pre-dosing, approx. 2 hours):** Takes place on the **Friday** immediately before your Dosing Day, at **26 Bedford Way, London, WC1H 0AP**.
- **Visit 3 (Dosing Day, 10:00–18:00):** Your main all-day visit on a **Saturday**, at **1-19 Torrington Place, WC1E 7HB**. You will arrive at **10:00** and be collected at approximately **18:00**.
- **Visit 4 (Follow-up, approx. 3 hours):** Takes place on a **Monday**, approximately two weeks after your Dosing Day, at **26 Bedford Way, London, WC1H 0AP**.
""")
st.divider()

# --- 6. UI: TABS ---
tab1, tab2 = st.tabs(["**🗓️ Book Appointment**", "**⚙️ Admin Panel**"])

with tab1:
    st.header("Book Your Appointments")

    st.subheader("Step 1: Your Information")
    col1, col2 = st.columns(2)
    name = col1.text_input("Full Name *")
    participant_id = col1.text_input("Participant ID *")
    email = col2.text_input("Email Address *")

    if name and participant_id and email:
        st.subheader("Step 2: Select Your Dosing Date")
        dosing_dates = booking_system.get_dosing_dates()
        dosing_date = st.selectbox(
            "Select an available **Saturday** Dosing Date (Visit 3):",
            dosing_dates,
            format_func=lambda x: x.strftime("%A, %B %d, %Y"),
            index=None,
            placeholder="Choose a date from the list"
        )

        if dosing_date:
            baseline_date = booking_system.get_baseline_date(dosing_date)
            pre_dosing_date = booking_system.get_pre_dosing_date(dosing_date)
            follow_up_date = booking_system.get_follow_up_date(dosing_date)

            st.info(
                f"**Your automatically generated visit dates:**\n\n"
                f"- **V1 (Baseline, approx. 3 hours):** `{baseline_date.strftime('%A, %d %b %Y')}`\n\n"
                f"- **V2 (Pre-dosing, approx. 2 hours):** `{pre_dosing_date.strftime('%A, %d %b %Y')}`\n\n"
                f"- **V3 (Dosing Day, 10:00–18:00):** `{dosing_date.strftime('%A, %d %b %Y')}`\n\n"
                f"- **V4 (Follow-up, approx. 3 hours):** `{follow_up_date.strftime('%A, %d %b %Y')}`"
            )

            st.subheader("Step 3: Choose Start Times for Your Visits")

            available_v1_times = booking_system.get_available_baseline_slots(baseline_date)
            available_v2_times = booking_system.get_available_pre_dosing_slots(pre_dosing_date)
            available_v4_times = booking_system.get_available_follow_up_slots(follow_up_date)

            any_unavailable = False
            if not available_v1_times:
                st.error(f"No available 3-hour slots for Visit 1 on {baseline_date.strftime('%A, %d %b')}. Please select a different Dosing Date.", icon="❌")
                any_unavailable = True
            if not available_v2_times:
                st.error(f"No available 2-hour slots for Visit 2 on {pre_dosing_date.strftime('%A, %d %b')}. Please select a different Dosing Date.", icon="❌")
                any_unavailable = True
            if not available_v4_times:
                st.error(f"No available 3-hour slots for Visit 4 on {follow_up_date.strftime('%A, %d %b')}. Please select a different Dosing Date.", icon="❌")
                any_unavailable = True

            if not any_unavailable:
                col1, col2, col3 = st.columns(3)
                baseline_time = col1.selectbox("Visit 1 start time (Baseline, Tue):", available_v1_times)
                pre_dosing_time = col2.selectbox("Visit 2 start time (Pre-dosing, Fri):", available_v2_times)
                follow_up_time = col3.selectbox("Visit 4 start time (Follow-up, Mon):", available_v4_times)

                st.divider()
                if st.button("✅ **Confirm and Book All Appointments**", type="primary", use_container_width=True):
                    with st.spinner("Booking your appointments..."):
                        booking_details = {
                            'name': name,
                            'participant_id': participant_id,
                            'email': email,
                            'baseline_date': baseline_date.strftime('%Y-%m-%d'),
                            'baseline_time': baseline_time,
                            'pre_dosing_date': pre_dosing_date.strftime('%Y-%m-%d'),
                            'pre_dosing_time': pre_dosing_time,
                            'dosing_date': dosing_date.strftime('%Y-%m-%d'),
                            'dosing_time': '10:00-18:00',
                            'follow_up_date': follow_up_date.strftime('%Y-%m-%d'),
                            'follow_up_time': follow_up_time,
                            'booking_status': 'Active',
                            'notes': '',
                            'booking_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'cancellation_time': ''
                        }
                        success, message = booking_system.book_participant(booking_details)
                        if success:
                            st.success("Booking Confirmed!")
                            st.balloons()
                            st.info("**Reminder:** Please add these dates to your calendar. A member of the research team will be in touch to confirm and send calendar invites.", icon="🔔")
                        else:
                            st.error(f"Booking Failed: {message}")

with tab2:
    st.header("Admin Panel")
    password = st.text_input("Enter Admin Password", type="password", key="admin_password")
    admin_password = st.secrets.get("admin_password", "admin123")

    if password == admin_password:
        st.success("Access Granted", icon="🔓")
        admin_tab1, admin_tab2, admin_tab3 = st.tabs([
            "**View Bookings**", "**Cancel a Booking**", "**Sheet Setup**"
        ])

        with admin_tab1:
            st.subheader("All Participant Bookings")
            if st.button("🔄 Refresh Data from Google Sheets"):
                st.cache_resource.clear()
                st.rerun()
            st.dataframe(booking_system.bookings, use_container_width=True)

        with admin_tab2:
            st.subheader("Cancel an Existing Booking")
            # Refresh bookings from sheet before displaying
            active_bookings = booking_system.bookings[booking_system.bookings['booking_status'] == 'Active']
            if active_bookings.empty:
                st.info("No active bookings found. If you expect to see bookings here, use the **Sheet Setup** tab to reset headers and try again.")
            else:
                options = {
                    f"{row['participant_id']} — {row['name']} (Dosing: {row['dosing_date']})": row['participant_id']
                    for _, row in active_bookings.iterrows()
                }
                selected_display = st.selectbox("Select a booking to cancel:", options.keys())
                reason = st.text_input("Reason for cancellation:")
                if st.button("🗑️ Cancel Selected Booking", type="primary"):
                    if not reason:
                        st.error("A reason for cancellation is required.")
                    else:
                        participant_id_to_cancel = options[selected_display]
                        with st.spinner("Cancelling booking..."):
                            success, message = booking_system.cancel_booking(participant_id_to_cancel, reason)
                            if success:
                                st.success(message)
                                st.rerun()
                            else:
                                st.error(message)

        with admin_tab3:
            st.subheader("Reset Sheet Headers")
            st.warning(
                "Use this if the Google Sheet has old or mismatched headers (e.g. from a previous version of the app). "
                "This will **clear the entire sheet** and write fresh headers. Only use this when there are no bookings to preserve.",
                icon="⚠️"
            )
            st.markdown("The new headers will be:")
            st.code(", ".join(SHEET_HEADERS))
            if st.button("🔧 Reset Sheet Headers Now", type="primary"):
                with st.spinner("Resetting headers..."):
                    success, message = booking_system.initialise_sheet_headers()
                    if success:
                        st.success(message)
                        st.cache_resource.clear()
                        st.rerun()
                    else:
                        st.error(message)

    elif password:
        st.error("Incorrect password.", icon="🔒")

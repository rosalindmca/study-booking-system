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
COLUMNS = [
    'name', 'participant_id', 'email',
    'baseline_date', 'baseline_time',
    'pre_dosing_date', 'pre_dosing_time',
    'dosing_date', 'dosing_time',
    'follow_up_date', 'follow_up_time',
    'booking_status', 'notes', 'booking_time', 'cancellation_time'
]

SHEET_HEADERS = [
    'Name', 'Participant ID', 'Email',
    'V1 Date (Baseline)', 'V1 Start Time',
    'V2 Date (Pre-dosing)', 'V2 Start Time',
    'V3 Date (Dosing Day)', 'V3 Time',
    'V4 Date (Follow-up)', 'V4 Start Time',
    'Status', 'Notes', 'Booking Made', 'Cancellation Time'
]

HEADER_TO_KEY = dict(zip(SHEET_HEADERS, COLUMNS))

# Wednesday dosing dates for W group
WEDNESDAY_DOSING_DATES = [
    datetime(2026, 5, 20).date(),
    datetime(2026, 5, 27).date(),
    datetime(2026, 6, 3).date(),
    datetime(2026, 6, 10).date(),
    datetime(2026, 6, 17).date(),
    datetime(2026, 6, 24).date(),
    datetime(2026, 7, 15).date(),
    datetime(2026, 7, 22).date(),
    datetime(2026, 8, 12).date(),
    datetime(2026, 9, 16).date(),
]


# --- 2. GOOGLE SHEETS CONNECTION ---
# Only credentials are cached — they never change.
# The sheet object itself is never cached so data is always fresh on every page load.
@st.cache_resource
def get_credentials():
    try:
        if "google_sheets" not in st.secrets:
            return None
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        return ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["google_sheets"], scope)
    except Exception as e:
        st.sidebar.error(f"Credentials error: {e}")
        return None


def get_gsheet():
    """Returns a fresh sheet connection on every call. Never cached."""
    st.sidebar.title("DIPP Booking System")
    st.sidebar.caption("Version 7.2")
    try:
        creds = get_credentials()
        if creds is None:
            st.sidebar.error("Google Sheets credentials not found in secrets.")
            return None
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
        """Reads fresh data directly from Google Sheets every time it is called."""
        try:
            all_cells = self.sheet.get_all_values()
            if not all_cells or len(all_cells) < 1:
                return
            raw_headers = all_cells[0]
            data = all_cells[1:]
            if not data:
                return
            mapped_headers = [HEADER_TO_KEY.get(h, h) for h in raw_headers]
            df = pd.DataFrame(data, columns=mapped_headers)
            known_cols = [c for c in COLUMNS if c in df.columns]
            self.bookings = df[known_cols].reindex(columns=COLUMNS, fill_value="")
        except Exception as e:
            st.warning(f"Could not read sheet data: {e}")

    def initialise_sheet_headers(self):
        try:
            self.sheet.clear()
            self.sheet.update('A1', [SHEET_HEADERS])
            self._load_bookings_from_sheet()
            return True, "Sheet headers reset successfully."
        except Exception as e:
            return False, f"Failed to reset headers: {e}"

    # --- GROUP DETECTION ---
    def get_group(self, dosing_date):
        """W = Wednesday dosing, S = Saturday dosing."""
        return 'W' if dosing_date.weekday() == 2 else 'S'

    # --- DOSING DATES ---
    def get_dosing_dates(self):
        """Returns all available dosing dates: specific Wednesdays (W) + Saturdays May–Sep 2026 (S).
        Any date that already has an active booking is excluded."""
        # Build Saturday list
        start_date = datetime(2026, 5, 2).date()
        end_date = datetime(2026, 9, 30).date()
        saturday_dates = []
        for i in range((end_date - start_date).days + 1):
            d = start_date + timedelta(days=i)
            if d.weekday() == 5:
                saturday_dates.append(d)

        all_dates = sorted(WEDNESDAY_DOSING_DATES + saturday_dates)

        # Get already-booked dosing dates
        booked_dates = set()
        if not self.bookings.empty:
            active = self.bookings[self.bookings['booking_status'] == 'Active']
            for date_str in active['dosing_date'].dropna():
                try:
                    booked_dates.add(datetime.strptime(date_str, '%Y-%m-%d').date())
                except (ValueError, TypeError):
                    pass

        return [d for d in all_dates if d not in booked_dates]

    # --- DATE CALCULATIONS ---
    def get_baseline_date(self, dosing_date):
        """
        W group: most recent Monday at least 21 days before dosing Wednesday.
        S group: most recent Tuesday at least 21 days before dosing Saturday.
        """
        group = self.get_group(dosing_date)
        anchor = dosing_date - timedelta(days=21)
        target = 0 if group == 'W' else 1  # Monday=0, Tuesday=1
        while anchor.weekday() != target:
            anchor -= timedelta(days=1)
        return anchor

    def get_pre_dosing_date(self, dosing_date):
        """
        W group: Tuesday immediately before Wednesday.
        S group: Friday immediately before Saturday.
        In both cases this is simply dosing_date - 1 day.
        """
        return dosing_date - timedelta(days=1)

    def get_follow_up_date(self, dosing_date):
        """
        W group: nearest Thursday on or after dosing + 14 days.
        S group: nearest Monday on or after dosing + 14 days.
        """
        group = self.get_group(dosing_date)
        anchor = dosing_date + timedelta(days=14)
        target = 3 if group == 'W' else 0  # Thursday=3, Monday=0
        while anchor.weekday() != target:
            anchor += timedelta(days=1)
        return anchor

    # --- SLOT AVAILABILITY ---
    def _get_available_slots(self, visit_date, date_col, time_col, duration_hours, start_str, end_str):
        """Returns list of available HH:MM start times for a given visit date and window.
        Excludes any times that would overlap with an existing active booking."""
        slot_duration = timedelta(hours=duration_hours)
        start_time = datetime.strptime(start_str, "%H:%M")
        end_time = datetime.strptime(end_str, "%H:%M")

        # Generate all potential 30-min slots within the window
        potential_slots = []
        current = start_time
        while current <= end_time:
            potential_slots.append(current)
            current += timedelta(minutes=30)

        # Find already-booked intervals on this date
        booked_intervals = []
        if not self.bookings.empty:
            date_str = visit_date.strftime('%Y-%m-%d')
            day_bookings = self.bookings[
                (self.bookings['booking_status'] == 'Active') &
                (self.bookings[date_col] == date_str)
            ]
            for _, row in day_bookings.iterrows():
                try:
                    bs = datetime.strptime(row[time_col], "%H:%M")
                    booked_intervals.append((bs, bs + slot_duration))
                except (ValueError, TypeError):
                    continue

        # Return slots that don't overlap any booked interval
        available = []
        for ps in potential_slots:
            pe = ps + slot_duration
            if all(not (max(ps, bs) < min(pe, be)) for bs, be in booked_intervals):
                available.append(ps.strftime("%H:%M"))
        return available

    def get_available_baseline_slots(self, baseline_date, group):
        """
        W group (Monday): 09:00–14:00, 3hr session, finish by 17:00.
        S group (Tuesday evening): 16:00–17:00, 3hr session, finish by 20:00.
        """
        if group == 'W':
            return self._get_available_slots(baseline_date, 'baseline_date', 'baseline_time', 3, "09:00", "14:00")
        else:
            return self._get_available_slots(baseline_date, 'baseline_date', 'baseline_time', 3, "16:00", "17:00")

    def get_available_pre_dosing_slots(self, pre_dosing_date, group):
        """Both groups: 09:00–15:00, 2hr session, finish by 17:00."""
        return self._get_available_slots(pre_dosing_date, 'pre_dosing_date', 'pre_dosing_time', 2, "09:00", "15:00")

    def get_available_follow_up_slots(self, follow_up_date, group):
        """
        W group (Thursday): 09:00–14:00, 3hr session, finish by 17:00.
        S group (Monday evening): 16:00–17:00, 3hr session, finish by 20:00.
        """
        if group == 'W':
            return self._get_available_slots(follow_up_date, 'follow_up_date', 'follow_up_time', 3, "09:00", "14:00")
        else:
            return self._get_available_slots(follow_up_date, 'follow_up_date', 'follow_up_time', 3, "16:00", "17:00")

    # --- BOOKING ---
    def book_participant(self, details):
        # Step 1: Always reload fresh data from the sheet immediately before any checks.
        # This means even if two people are on the page simultaneously, whoever clicks
        # second will see the first person's booking and be blocked.
        self._load_bookings_from_sheet()

        # Step 2: Hard check — is this dosing date already taken?
        # This is the primary guard against double-booking the same dosing day.
        if not self.bookings.empty:
            active_dosing_dates = set(
                self.bookings[self.bookings['booking_status'] == 'Active']['dosing_date'].values
            )
            if details['dosing_date'] in active_dosing_dates:
                return False, (
                    f"The dosing date {details['dosing_date']} has already been booked by another participant. "
                    "Please go back and select a different date."
                )

        # Step 3: Check for duplicate participant ID
        if not self.bookings.empty:
            active_ids = set(self.bookings[self.bookings['booking_status'] == 'Active']['participant_id'].values)
            if details['participant_id'] in active_ids:
                return False, "This Participant ID already has an active booking."

        # Step 4: Re-check that the chosen V1/V2/V4 time slots are still available
        group = self.get_group(datetime.strptime(details['dosing_date'], '%Y-%m-%d').date())
        baseline_date = datetime.strptime(details['baseline_date'], '%Y-%m-%d').date()
        pre_dosing_date = datetime.strptime(details['pre_dosing_date'], '%Y-%m-%d').date()
        follow_up_date = datetime.strptime(details['follow_up_date'], '%Y-%m-%d').date()

        if details['baseline_time'] not in self.get_available_baseline_slots(baseline_date, group):
            return False, f"Visit 1 slot {details['baseline_time']} on {details['baseline_date']} has just been taken. Please go back and choose another time."
        if details['pre_dosing_time'] not in self.get_available_pre_dosing_slots(pre_dosing_date, group):
            return False, f"Visit 2 slot {details['pre_dosing_time']} on {details['pre_dosing_date']} has just been taken. Please go back and choose another time."
        if details['follow_up_time'] not in self.get_available_follow_up_slots(follow_up_date, group):
            return False, f"Visit 4 slot {details['follow_up_time']} on {details['follow_up_date']} has just been taken. Please go back and choose another time."

        # Step 5: All checks passed — write to sheet
        if self.sheet:
            row_to_save = [details.get(col, "") for col in COLUMNS]
            self.sheet.append_row(row_to_save, value_input_option='USER_ENTERED')
            self._load_bookings_from_sheet()
            return True, "Booking successful!"
        else:
            return False, "Booking failed: No connection to Google Sheets."

    # --- CANCELLATION ---
    def cancel_booking(self, participant_id, reason):
        if not self.sheet:
            return False, "Cannot cancel: No connection to Google Sheets"
        try:
            col_b_values = self.sheet.col_values(2)
            if participant_id not in col_b_values:
                return False, f"Could not find booking for Participant ID: {participant_id}"

            row_number = col_b_values.index(participant_id) + 1
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
# Fresh connection + fresh data on every page load. No stale state possible.
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

There are two dosing groups:
- **Wednesday group (W):** Dosing takes place on a Wednesday. All visits run during the day.
- **Saturday group (S):** Dosing takes place on a Saturday. Visits 1 and 4 take place on weekday evenings.

| Visit | W Group | S Group |
|---|---|---|
| **V1 Baseline (~3 hrs)** | Monday daytime (09:00–17:00), ≥3 weeks before dosing | Tuesday evening (16:00–20:00), ≥3 weeks before dosing |
| **V2 Pre-dosing (~2 hrs)** | Tuesday daytime (09:00–17:00), day before dosing | Friday daytime (09:00–17:00), day before dosing |
| **V3 Dosing Day (09:00–18:00)** | Wednesday | Saturday |
| **V4 Follow-up (~3 hrs)** | Thursday daytime (09:00–17:00), ~2 weeks after dosing | Monday evening (16:00–20:00), ~2 weeks after dosing |

All visits take place at **26 Bedford Way, London, WC1H 0AP**, except Dosing Day which is at **1-19 Torrington Place, WC1E 7HB**.
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

        def format_dosing_date(d):
            group = booking_system.get_group(d)
            label = "W group (Wednesday dosing)" if group == 'W' else "S group (Saturday dosing)"
            return f"{d.strftime('%A, %d %B %Y')} — {label}"

        dosing_date = st.selectbox(
            "Select an available Dosing Date (Visit 3):",
            dosing_dates,
            format_func=format_dosing_date,
            index=None,
            placeholder="Choose a date from the list"
        )

        if dosing_date:
            group = booking_system.get_group(dosing_date)
            baseline_date = booking_system.get_baseline_date(dosing_date)
            pre_dosing_date = booking_system.get_pre_dosing_date(dosing_date)
            follow_up_date = booking_system.get_follow_up_date(dosing_date)

            if group == 'W':
                v1_label = "V1 Baseline (~3 hrs, Monday, daytime)"
                v2_label = "V2 Pre-dosing (~2 hrs, Tuesday, daytime)"
                v3_label = "V3 Dosing Day (09:00–18:00, Wednesday)"
                v4_label = "V4 Follow-up (~3 hrs, Thursday, daytime)"
            else:
                v1_label = "V1 Baseline (~3 hrs, Tuesday, evening)"
                v2_label = "V2 Pre-dosing (~2 hrs, Friday, daytime)"
                v3_label = "V3 Dosing Day (09:00–18:00, Saturday)"
                v4_label = "V4 Follow-up (~3 hrs, Monday, evening)"

            st.info(
                f"**Your automatically generated visit dates ({group} group):**\n\n"
                f"- **{v1_label}:** `{baseline_date.strftime('%A, %d %b %Y')}`\n\n"
                f"- **{v2_label}:** `{pre_dosing_date.strftime('%A, %d %b %Y')}`\n\n"
                f"- **{v3_label}:** `{dosing_date.strftime('%A, %d %b %Y')}`\n\n"
                f"- **{v4_label}:** `{follow_up_date.strftime('%A, %d %b %Y')}`"
            )

            st.subheader("Step 3: Choose Start Times for Your Visits")

            available_v1_times = booking_system.get_available_baseline_slots(baseline_date, group)
            available_v2_times = booking_system.get_available_pre_dosing_slots(pre_dosing_date, group)
            available_v4_times = booking_system.get_available_follow_up_slots(follow_up_date, group)

            any_unavailable = False
            if not available_v1_times:
                st.error(f"No available slots for Visit 1 on {baseline_date.strftime('%A, %d %b')}. Please select a different Dosing Date.", icon="❌")
                any_unavailable = True
            if not available_v2_times:
                st.error(f"No available slots for Visit 2 on {pre_dosing_date.strftime('%A, %d %b')}. Please select a different Dosing Date.", icon="❌")
                any_unavailable = True
            if not available_v4_times:
                st.error(f"No available slots for Visit 4 on {follow_up_date.strftime('%A, %d %b')}. Please select a different Dosing Date.", icon="❌")
                any_unavailable = True

            if not any_unavailable:
                col1, col2, col3 = st.columns(3)
                baseline_time = col1.selectbox(f"Visit 1 start time ({baseline_date.strftime('%a %d %b')}):", available_v1_times)
                pre_dosing_time = col2.selectbox(f"Visit 2 start time ({pre_dosing_date.strftime('%a %d %b')}):", available_v2_times)
                follow_up_time = col3.selectbox(f"Visit 4 start time ({follow_up_date.strftime('%a %d %b')}):", available_v4_times)

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
                            'dosing_time': '09:00-18:00',
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
                st.rerun()
            st.dataframe(booking_system.bookings, use_container_width=True)

        with admin_tab2:
            st.subheader("Cancel an Existing Booking")
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
                "Use this if the Google Sheet has old or mismatched headers. "
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
                        st.rerun()
                    else:
                        st.error(message)

    elif password:
        st.error("Incorrect password.", icon="🔒")

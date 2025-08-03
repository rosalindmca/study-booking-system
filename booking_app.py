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

# --- 2. GOOGLE SHEETS CONNECTION ---
@st.cache_resource
def get_gsheet():
    """Connects to Google Sheets and returns the sheet object, cached."""
    st.sidebar.title("DIPP Booking System")
    st.sidebar.caption("Version 4.0 (Complete)")
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
    """Handles all booking logic, data loading, and date calculations."""
    def __init__(self, sheet_connection):
        self.sheet = sheet_connection
        self.columns = [
            'name', 'participant_id', 'email', 'group', 'baseline_date', 'baseline_time',
            'pre_dosing_date', 'pre_dosing_time', 'dosing_date', 'dosing_time',
            'follow_up_date', 'follow_up_time', 'booking_status', 'notes', 'booking_time',
            'cancellation_time'
        ]
        self.bookings = pd.DataFrame(columns=self.columns)
        if self.sheet:
            self._load_bookings_from_sheet()

    def _load_bookings_from_sheet(self):
        """Loads all records from the Google Sheet into a pandas DataFrame."""
        try:
            all_cells = self.sheet.get_all_values()
            if not all_cells:
                self.sheet.update('A1', [self.columns])
                return
            
            headers, data = all_cells[0], all_cells[1:]
            if data:
                self.bookings = pd.DataFrame(data, columns=headers)
        except Exception as e:
            st.warning(f"Could not read sheet data: {e}")

    def get_dosing_dates(self, group):
        """Returns a list of available dosing dates for a specific group."""
        start_date, end_date = datetime(2025, 5, 1).date(), datetime(2025, 11, 29).date()
        target_day = 2 if group == 'WEDNESDAY' else 5
        
        valid_dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1) if (start_date + timedelta(days=i)).weekday() == target_day]
        
        booked_dates = []
        if not self.bookings.empty:
            active_bookings = self.bookings[self.bookings['booking_status'] == 'Active']
            for date_str in active_bookings['dosing_date'].dropna():
                try:
                    booked_dates.append(datetime.strptime(date_str, '%Y-%m-%d').date())
                except (ValueError, TypeError):
                    pass
        return [d for d in valid_dates if d not in booked_dates]

    def get_pre_scan_date(self, dosing_date):
        return dosing_date - timedelta(days=1)
    
    def get_follow_up_date(self, dosing_date, group):
        follow_up = dosing_date + timedelta(days=14)
        target_day = 3 if group == 'WEDNESDAY' else 6
        while follow_up.weekday() != target_day:
            follow_up += timedelta(days=1)
        return follow_up

    def get_baseline_date(self, dosing_date):
        current = dosing_date - timedelta(days=22)
        while current.weekday() != 0:
            current -= timedelta(days=1)
        return current

    def generate_daily_time_slots(self):
        """Generates a static list of start times from 09:00 to 18:30."""
        slots = []
        start_time = datetime.strptime("09:00", "%H:%M")
        end_time = datetime.strptime("18:30", "%H:%M") # New end time as requested
        
        current_slot = start_time
        while current_slot <= end_time:
            slots.append(current_slot.strftime("%H:%M"))
            current_slot += timedelta(minutes=30)
        return slots

    def check_baseline_availability(self, baseline_date, group):
        if self.bookings.empty: return True
        time_slot = "Daytime" if group == "WEDNESDAY" else "Evening"
        date_str = baseline_date.strftime('%Y-%m-%d')
        match = self.bookings[(self.bookings['booking_status'] == 'Active') & (self.bookings['baseline_date'] == date_str) & (self.bookings['baseline_time'] == time_slot)]
        return match.empty

    def book_participant(self, details):
        if not self.bookings.empty and details['participant_id'] in self.bookings[self.bookings['booking_status'] == 'Active']['participant_id'].values:
            return False, "This Participant ID already has an active booking."
        
        if self.sheet:
            row_to_save = [details.get(col, "") for col in self.columns]
            self.sheet.append_row(row_to_save, value_input_option='USER_ENTERED')
            self._load_bookings_from_sheet()
            return True, "Booking successful!"
        else:
            return False, "Booking failed: No connection to Google Sheets."
            
    def cancel_booking(self, participant_id, reason):
        if not self.sheet: return False, "Cannot cancel: No connection to Google Sheets"
        try:
            cell = self.sheet.find(participant_id)
            if not cell: return False, f"Could not find booking for participant ID: {participant_id}"
            row_number = cell.row
            headers = self.sheet.row_values(1)
            status_col = headers.index('booking_status') + 1
            notes_col = headers.index('notes') + 1
            cancel_time_col = headers.index('cancellation_time') + 1
            self.sheet.update_cell(row_number, status_col, 'Cancelled')
            self.sheet.update_cell(row_number, notes_col, f"Cancelled: {reason}")
            self.sheet.update_cell(row_number, cancel_time_col, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            self._load_bookings_from_sheet()
            return True, "Booking cancelled successfully"
        except Exception as e:
            return False, f"Error during cancellation: {e}"

# --- 4. INITIALIZE SYSTEM ---
gsheet_connection = get_gsheet()
if gsheet_connection:
    booking_system = StudyBookingSystem(gsheet_connection)
else:
    st.error("The booking system could not be initialized. Please check the Google Sheets connection and credentials.")
    st.stop()

# --- 5. UI: TITLE AND INFORMATION ---
st.title("DIPP Study Participant Booking System")
st.markdown("""
### About the DIPP study visits
The DIPP study requires participants to attend four separate visits:
1.  **Baseline Visit (Visit 1)**: About 3 weeks before your dosing day, you'll come in for your first baseline visit to do surveys and computer tasks (about 3 hours). **Location: 26 Bedford Way, London, WC1H 0AP**
2.  **Pre-dosing Visit (Visit 2)**: One day before your dosing, you'll need to come in for about **5 hours** to complete surveys, computer tasks, and have an fMRI movie scan. **Location: 26 Bedford Way, London, WC1H 0AP**
3.  **Dosing Day (Visit 3)**: This is the main visit where you'll spend all day at the center. **Location: 1-19 Torrington Place, London, WC1E 7HB**
4.  **Follow-up Visit (Visit 4)**: About 2 weeks after your dosing day, you'll come in for about **5 hours** to complete surveys, computer tasks, and have an fMRI movie scan. **Location: 26 Bedford Way, London, WC1H 0AP**
---
### Our Scheduling System
We have two scheduling groups based on your chosen Dosing Day:
#### Wednesday Dosing Group:
- **Dosing Day**: Wednesday | **Pre-dosing Visit**: Tuesday | **Baseline Visit**: Monday (Daytime) | **Follow-up Visit**: Thursday
#### Saturday Dosing Group:
- **Dosing Day**: Saturday | **Pre-dosing Visit**: Friday | **Baseline Visit**: Monday (Evening) | **Follow-up Visit**: Sunday
""")
st.divider()

# --- 6. UI: BOOKING AND ADMIN TABS ---
tab1, tab2 = st.tabs(["**🗓️ Book Appointment**", "**⚙️ Admin Panel**"])

with tab1:
    st.header("Book Your Appointments")
    
    # --- Step 1: Participant Info ---
    st.subheader("Step 1: Your Information")
    col1, col2 = st.columns(2)
    name = col1.text_input("Full Name *", key="name_input")
    participant_id = col1.text_input("Participant ID *", key="id_input")
    email = col2.text_input("Email Address *", key="email_input")

    # --- Subsequent steps only appear if initial info is provided ---
    if name and participant_id and email:
        st.subheader("Step 2: Select Your Schedule")
        group = st.radio("Choose your preferred dosing day group:", ["WEDNESDAY", "SATURDAY"], key="group_select", horizontal=True)
        dosing_dates = booking_system.get_dosing_dates(group)
        dosing_date = st.selectbox(
            f"Select an available **{group.capitalize()}** Dosing Date (Visit 3):",
            dosing_dates,
            format_func=lambda x: x.strftime("%A, %B %d, %Y"),
            index=None,
            placeholder="Choose a date from the list"
        )

        if dosing_date:
            baseline_date = booking_system.get_baseline_date(dosing_date)
            pre_dosing_date = booking_system.get_pre_scan_date(dosing_date)
            follow_up_date = booking_system.get_follow_up_date(dosing_date, group)
            baseline_time = "Daytime" if group == "WEDNESDAY" else "Evening"
            is_baseline_available = booking_system.check_baseline_availability(baseline_date, group)

            st.info(f"**Your automatically generated schedule:**\n\n"
                    f"- **V1 (Baseline):** `{baseline_date.strftime('%A, %d %b %Y')}` at `{baseline_time}`\n\n"
                    f"- **V2 (Pre-dosing):** `{pre_dosing_date.strftime('%A, %d %b %Y')}`\n\n"
                    f"- **V3 (Dosing Day):** `{dosing_date.strftime('%A, %d %b %Y')}` (All Day)\n\n"
                    f"- **V4 (Follow-up):** `{follow_up_date.strftime('%A, %d %b %Y')}`")

            if not is_baseline_available:
                st.error(f"The required Baseline slot ({baseline_time} on {baseline_date.strftime('%d %b')}) is already booked. Please select a different Dosing Date above.", icon="❌")
            else:
                st.subheader("Step 3: Choose Start Times for Your 5-Hour Sessions")
                col3, col4 = st.columns(2)
                available_times = booking_system.generate_daily_time_slots()
                pre_dosing_time = col3.selectbox("Choose a start time for Visit 2:", available_times, key="v2_time")
                follow_up_time = col4.selectbox("Choose a start time for Visit 4:", available_times, key="v4_time")
                
                st.divider()
                if st.button("✅ **Confirm and Book All Appointments**", type="primary", use_container_width=True):
                    with st.spinner("Booking your appointments..."):
                        booking_details = {
                            'name': name, 'participant_id': participant_id, 'email': email, 'group': group,
                            'baseline_date': baseline_date.strftime('%Y-%m-%d'), 'baseline_time': baseline_time,
                            'pre_dosing_date': pre_dosing_date.strftime('%Y-%m-%d'), 'pre_dosing_time': pre_dosing_time,
                            'dosing_date': dosing_date.strftime('%Y-%m-%d'), 'dosing_time': 'All Day',
                            'follow_up_date': follow_up_date.strftime('%Y-%m-%d'), 'follow_up_time': follow_up_time,
                            'booking_status': 'Active', 'notes': '', 'booking_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'cancellation_time': ''
                        }
                        success, message = booking_system.book_participant(booking_details)
                        if success:
                            st.success("Booking Confirmed! Please write these dates in your calendar.")
                            st.balloons()
                        else:
                            st.error(f"Booking Failed: {message}")

with tab2:
    st.header("Admin Panel")
    password = st.text_input("Enter Admin Password", type="password", key="admin_password")
    admin_password = st.secrets.get("admin_password", "admin123") # Default password if not in secrets

    if password == admin_password:
        st.success("Access Granted", icon="🔓")
        admin_tab1, admin_tab2 = st.tabs(["**View Bookings**", "**Cancel a Booking**"])
        
        with admin_tab1:
            st.subheader("All Participant Bookings")
            if st.button("🔄 Refresh Data from Google Sheets"):
                st.cache_resource.clear()
                st.rerun()
            st.dataframe(booking_system.bookings, use_container_width=True)

        with admin_tab2:
            st.subheader("Cancel an Existing Booking")
            active_bookings = booking_system.bookings[booking_system.bookings['booking_status'] == 'Active']
            if active_bookings.empty:
                st.info("No active bookings to cancel.")
            else:
                options = {f"{row['participant_id']} - {row['name']}": row['participant_id'] for _, row in active_bookings.iterrows()}
                selected_display = st.selectbox("Select a booking to cancel:", options.keys())
                reason = st.text_input("Reason for cancellation:")
                if st.button("🗑️ Cancel Selected Booking", type="primary"):
                    if not reason: st.error("A reason for cancellation is required.")
                    else:
                        participant_id_to_cancel = options[selected_display]
                        with st.spinner("Cancelling booking..."):
                            success, message = booking_system.cancel_booking(participant_id_to_cancel, reason)
                            if success: st.success(message); st.rerun()
                            else: st.error(message)
    elif password:
        st.error("Incorrect password.", icon="🔒")
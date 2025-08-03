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
    st.sidebar.caption("Version 3.0 (Interactive)")
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
        target_day = 2 if group == 'WEDNESDAY' else 5 # Wednesday or Saturday
        
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
        """V2 Date: Exactly one day before the dosing date."""
        return dosing_date - timedelta(days=1)
    
    def get_follow_up_date(self, dosing_date, group):
        """V4 Date: Finds the correct Thursday/Sunday ~14 days after dosing."""
        follow_up = dosing_date + timedelta(days=14)
        target_day = 3 if group == 'WEDNESDAY' else 6 # Thursday or Sunday
        while follow_up.weekday() != target_day:
            follow_up += timedelta(days=1)
        return follow_up

    def get_baseline_date(self, dosing_date):
        """V1 Date: Finds the Monday that is at least 22 days before dosing."""
        current = dosing_date - timedelta(days=22)
        while current.weekday() != 0:
            current -= timedelta(days=1)
        return current

    def generate_daily_time_slots(self):
        """Generates a static list of start times for the 5-hour sessions."""
        slots = []
        start_time = datetime.strptime("09:00", "%H:%M")
        end_time = datetime.strptime("17:00", "%H:%M")
        
        current_slot = start_time
        while current_slot <= end_time:
            slots.append(current_slot.strftime("%H:%M"))
            current_slot += timedelta(minutes=30)
        return slots

    def check_baseline_availability(self, baseline_date, group):
        """Checks if the fixed Daytime/Evening baseline slot is already booked."""
        if self.bookings.empty: return True
        time_slot = "Daytime" if group == "WEDNESDAY" else "Evening"
        date_str = baseline_date.strftime('%Y-%m-%d')
        match = self.bookings[(self.bookings['booking_status'] == 'Active') & (self.bookings['baseline_date'] == date_str) & (self.bookings['baseline_time'] == time_slot)]
        return match.empty

    def book_participant(self, details):
        """Saves a new booking record to the Google Sheet."""
        if not self.bookings.empty and details['participant_id'] in self.bookings[self.bookings['booking_status'] == 'Active']['participant_id'].values:
            return False, "This Participant ID already has an active booking."
        
        if self.sheet:
            row_to_save = [details.get(col, "") for col in self.columns]
            self.sheet.append_row(row_to_save, value_input_option='USER_ENTERED')
            self._load_bookings_from_sheet() # Refresh local data
            return True, "Booking successful!"
        else:
            return False, "Booking failed: No connection to Google Sheets."

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

# --- 6. UI: INTERACTIVE BOOKING FLOW (NO FORM) ---
st.header("🗓️ Book Your Appointments")

# Step 1: Participant Info
st.subheader("Step 1: Your Information")
col1, col2 = st.columns(2)
name = col1.text_input("Full Name *", key="name_input")
participant_id = col1.text_input("Participant ID *", key="id_input")
email = col2.text_input("Email Address *", key="email_input")

# Subsequent steps only appear if initial info is provided
if name and participant_id and email:
    st.subheader("Step 2: Select Your Schedule")

    # Group selection triggers an immediate rerun to update the dosing date list
    group = st.radio("Choose your preferred dosing day group:", ["WEDNESDAY", "SATURDAY"], key="group_select", horizontal=True)

    dosing_dates = booking_system.get_dosing_dates(group)
    dosing_date = st.selectbox(
        f"Select an available **{group.capitalize()}** Dosing Date (Visit 3):",
        dosing_dates,
        format_func=lambda x: x.strftime("%A, %B %d, %Y"),
        index=None,
        placeholder="Choose a date"
    )

    # The rest of the UI appears only after a dosing date is selected
    if dosing_date:
        # Calculate all other dates based on the selected dosing date
        baseline_date = booking_system.get_baseline_date(dosing_date)
        pre_dosing_date = booking_system.get_pre_scan_date(dosing_date)
        follow_up_date = booking_system.get_follow_up_date(dosing_date, group)
        baseline_time = "Daytime" if group == "WEDNESDAY" else "Evening"
        is_baseline_available = booking_system.check_baseline_availability(baseline_date, group)

        # Display the full, calculated schedule
        st.info(
            f"""
            **Here is your automatically generated schedule:**
            - **V1 (Baseline):** `{baseline_date.strftime('%A, %d %b %Y')}` at `{baseline_time}`
            - **V2 (Pre-dosing):** `{pre_dosing_date.strftime('%A, %d %b %Y')}`
            - **V3 (Dosing Day):** `{dosing_date.strftime('%A, %d %b %Y')}` (All Day)
            - **V4 (Follow-up):** `{follow_up_date.strftime('%A, %d %b %Y')}`
            """
        )

        # Show an error and stop if the required baseline is unavailable
        if not is_baseline_available:
            st.error(f"The required Baseline slot ({baseline_time} on {baseline_date.strftime('%d %b')}) is already booked. Please select a different Dosing Date above.", icon="❌")
        else:
            # If baseline is available, show the time selectors
            st.subheader("Step 3: Choose Start Times for Visits 2 & 4")
            col3, col4 = st.columns(2)
            available_times = booking_system.generate_daily_time_slots()
            pre_dosing_time = col3.selectbox("Choose a start time for Visit 2:", available_times, key="v2_time")
            follow_up_time = col4.selectbox("Choose a start time for Visit 4:", available_times, key="v4_time")
            
            st.divider()

            # The final confirmation button
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
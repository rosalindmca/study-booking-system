import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 1. APP CONFIGURATION ---
st.set_page_config(
    page_title="DIPP Study Booking System",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. GOOGLE SHEETS CONNECTION ---
@st.cache_resource
def get_gsheet():
    """Connect to Google Sheets using credentials from st.secrets."""
    st.sidebar.title("DIPP Booking System")
    st.sidebar.caption("Version 2.0 (Stable)")
    try:
        if "google_sheets" not in st.secrets:
            st.sidebar.error("Google Sheets credentials not configured.")
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
    """Handles all booking logic, data loading, and calculations."""
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
        """Loads booking data from the connected Google Sheet."""
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
        """Gets available dosing dates, excluding any that are already booked."""
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

    def get_pre_scan_date(self, d_date): return d_date - timedelta(days=1)
    
    def get_follow_up_date(self, d_date, group):
        follow_up = d_date + timedelta(days=14)
        target_day = 3 if group == 'WEDNESDAY' else 6
        while follow_up.weekday() != target_day:
            follow_up += timedelta(days=1)
        return follow_up

    def get_baseline_date(self, d_date):
        current = d_date - timedelta(days=22)
        while current.weekday() != 0:
            current -= timedelta(days=1)
        return current

    def generate_daily_time_slots(self):
        """Generates a static list of start times for a 5-hour session."""
        slots = []
        start_time = datetime.strptime("09:00", "%H:%M")
        end_time = datetime.strptime("17:00", "%H:%M")
        
        current_slot = start_time
        while current_slot <= end_time:
            slots.append(current_slot.strftime("%H:%M"))
            current_slot += timedelta(minutes=30)
        return slots

    def check_baseline_availability(self, baseline_date, group):
        """Checks if the fixed Daytime/Evening baseline slot is available."""
        if self.bookings.empty: return True
        time_slot = "Daytime" if group == "WEDNESDAY" else "Evening"
        match = self.bookings[(self.bookings['booking_status'] == 'Active') & (self.bookings['baseline_date'] == baseline_date.strftime('%Y-%m-%d')) & (self.bookings['baseline_time'] == time_slot)]
        return match.empty

    def book_participant(self, details):
        """Validates and books a participant, saving the record to the sheet."""
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
        """Cancels a booking by updating its status."""
        if not self.sheet: return False, "Cannot cancel: No connection to Google Sheets"
        try:
            cell = self.sheet.find(participant_id)
            if not cell: return False, f"Could not find booking for participant ID: {participant_id}"
            row_number = cell.row
            headers = self.sheet.row_values(1)
            status_col, notes_col, cancel_time_col = headers.index('booking_status') + 1, headers.index('notes') + 1, headers.index('cancellation_time') + 1
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
    st.stop() # Stop the app if connection fails

# --- 5. UI: TITLE AND INFORMATION ---
st.title("DIPP Study Participant Booking System")

st.markdown("""
### About the DIPP study visits

The DIPP study requires participants to attend four separate visits:

1.  **Baseline Visit (Visit 1)**: About 3 weeks before your dosing day, you'll come in for your first baseline visit to do surveys and computer tasks (about 3 hours).  
    **Location: 26 Bedford Way, London, WC1H 0AP**

2.  **Pre-dosing Visit (Visit 2)**: One day before your dosing, you'll need to come in for about **5 hours** to complete surveys, computer tasks, and have an fMRI movie scan.  
    **Location: 26 Bedford Way, London, WC1H 0AP**

3.  **Dosing Day (Visit 3)**: This is the main visit where you'll spend all day at the center.  
    **Location: 1-19 Torrington Place, London, WC1E 7HB**

4.  **Follow-up Visit (Visit 4)**: About 2 weeks after your dosing day, you'll come in for about **5 hours** to complete surveys, computer tasks, and have an fMRI movie scan.  
    **Location: 26 Bedford Way, London, WC1H 0AP**

---
### Our Scheduling System

We have two scheduling groups based on your chosen Dosing Day:

#### Wednesday Dosing Group:
- **Dosing Day**: Wednesday (all day)
- **Pre-dosing Visit**: Tuesday (the day before). You will select a start time for your 5-hour session.
- **Baseline Visit**: Monday (at least 3 weeks before). Your session will be during the **Daytime**. The exact time will be confirmed via email.
- **Follow-up Visit**: Thursday (about 2 weeks after). You will select a start time for your 5-hour session.

#### Saturday Dosing Group:
- **Dosing Day**: Saturday (all day)
- **Pre-dosing Visit**: Friday (the day before). You will select a start time for your 5-hour session.
- **Baseline Visit**: Monday (at least 3 weeks before). Your session will be in the **Evening**. The exact time will be confirmed via email.
- **Follow-up Visit**: Sunday (about 2 weeks after). You will select a start time for your 5-hour session.

**Please use the form below to book your slot.** If you cannot attend any of the available slots, please contact the DIPP Research Team directly (dipp-project@ucl.ac.uk).
""")
st.divider()

# --- 6. UI: BOOKING AND ADMIN TABS ---
tab1, tab2 = st.tabs(["**🗓️ Book Appointment**", "**⚙️ Admin Panel**"])

with tab1:
    st.header("Book Your Appointments")
    with st.form("booking_form"):
        st.info("Please complete all steps below and click the 'Confirm' button at the bottom.", icon="👇")
        
        st.subheader("Step 1: Your Information")
        col1, col2 = st.columns(2)
        name = col1.text_input("Full Name *", help="Please enter your full name.")
        participant_id = col1.text_input("Participant ID *", help="Enter the ID provided to you by the research team.")
        email = col2.text_input("Email Address *", help="We will send a confirmation to this address.")

        st.subheader("Step 2: Select Your Dosing Day")
        group = st.radio("Choose your preferred dosing day group:", ["WEDNESDAY", "SATURDAY"], horizontal=True)
        
        dosing_dates = booking_system.get_dosing_dates(group)
        dosing_date = st.selectbox(
            f"Select an available **{group.capitalize()}** Dosing Date (Visit 3):",
            dosing_dates,
            format_func=lambda x: x.strftime("%A, %B %d, %Y"),
            index=0 if dosing_dates else None,
            placeholder="No available dates for this group"
        )

        if dosing_date:
            baseline_date = booking_system.get_baseline_date(dosing_date)
            if not booking_system.check_baseline_availability(baseline_date, group):
                st.error(f"The required Baseline slot for this Dosing Date ({baseline_date.strftime('%A, %d %b')}) is already booked. Please select a different Dosing Date.", icon="❌")
            else:
                pre_dosing_date = booking_system.get_pre_scan_date(dosing_date)
                follow_up_date = booking_system.get_follow_up_date(dosing_date, group)
                baseline_time = "Daytime" if group == "WEDNESDAY" else "Evening"

                st.subheader("Step 3: Choose Start Times for Visits 2 & 4")
                st.success(f"Your other appointments are automatically calculated. Your Baseline (Visit 1) is on **{baseline_date.strftime('%A, %d %b')}** in the **{baseline_time}**.", icon="✅")
                
                col1, col2 = st.columns(2)
                available_times = booking_system.generate_daily_time_slots()
                pre_dosing_time = col1.selectbox(f"Visit 2 Start Time (on {pre_dosing_date.strftime('%A, %d %b')}):", available_times)
                follow_up_time = col2.selectbox(f"Visit 4 Start Time (on {follow_up_date.strftime('%A, %d %b')}):", available_times)

        st.divider()
        submitted = st.form_submit_button("✅ **Confirm and Book All Appointments**", type="primary", use_container_width=True)

    if submitted:
        if not all([name, participant_id, email, dosing_date]):
            st.error("Please fill in all required fields (*) and select a dosing date before submitting.")
        elif not booking_system.check_baseline_availability(booking_system.get_baseline_date(dosing_date), group):
            st.error("Cannot book because the required Baseline slot is unavailable. Please select another Dosing Date.")
        else:
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
    password = st.text_input("Enter Admin Password", type="password")
    admin_password = st.secrets.get("admin_password", "admin123")

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
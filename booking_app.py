
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- APP CONFIGURATION ---
st.set_page_config(
    page_title="DIPP Study Booking System",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded"
)
st.sidebar.title("DIPP Booking System")
st.sidebar.caption("Version 1.4 (Stable)")

# --- GOOGLE SHEETS CONNECTION ---
@st.cache_resource
def get_gsheet():
    """Connect to Google Sheets using credentials from st.secrets."""
    try:
        if "google_sheets" not in st.secrets:
            st.sidebar.warning("⚠️ Google Sheets credentials not configured.")
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

sheet = get_gsheet()

# --- BACKEND LOGIC CLASS ---
class StudyBookingSystem:
    def __init__(self):
        """Initializes the booking system, defining columns and loading data."""
        self.columns = [
            'name', 'participant_id', 'email', 'group', 'baseline_date', 'baseline_time',
            'pre_dosing_date', 'pre_dosing_time', 'dosing_date', 'dosing_time',
            'follow_up_date', 'follow_up_time', 'booking_status', 'notes', 'booking_time',
            'cancellation_time'
        ]
        self.bookings = pd.DataFrame(columns=self.columns)
        if sheet:
            self._load_bookings_from_sheet()

    def _load_bookings_from_sheet(self):
        """Loads booking data from the connected Google Sheet."""
        try:
            all_cells = sheet.get_all_values()
            if not all_cells:
                # If the sheet is empty, write the headers
                sheet.update('A1', [self.columns])
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
        while current.weekday() != 0: # Monday
            current -= timedelta(days=1)
        return current

    def generate_daily_time_slots(self):
        """Generates a static list of start times for a 5-hour session."""
        slots = []
        start_time = datetime.strptime("09:00", "%H:%M")
        end_time = datetime.strptime("17:00", "%H:%M") # Latest start time
        
        current_slot = start_time
        while current_slot <= end_time:
            slots.append(current_slot.strftime("%H:%M"))
            current_slot += timedelta(minutes=30)
        return slots

    def check_baseline_availability(self, baseline_date, group):
        """Checks if the fixed Daytime/Evening baseline slot is available."""
        if self.bookings.empty:
            return True
        time_slot = "Daytime" if group == "WEDNESDAY" else "Evening"
        match = self.bookings[
            (self.bookings['booking_status'] == 'Active') &
            (self.bookings['baseline_date'] == baseline_date.strftime('%Y-%m-%d')) &
            (self.bookings['baseline_time'] == time_slot)
        ]
        return match.empty

    def book_participant(self, name, participant_id, email, group, baseline_date, pre_dosing_date, dosing_date, follow_up_date, pre_dosing_time, follow_up_time):
        """Books a participant and saves the record."""
        if not self.bookings.empty and participant_id in self.bookings[self.bookings['booking_status'] == 'Active']['participant_id'].values:
            return False, "This Participant ID already has an active booking."
        
        baseline_time = "Daytime" if group == "WEDNESDAY" else "Evening"
        booking_data = {
            'name': name, 'participant_id': participant_id, 'email': email, 'group': group,
            'baseline_date': baseline_date.strftime('%Y-%m-%d'), 'baseline_time': baseline_time,
            'pre_dosing_date': pre_dosing_date.strftime('%Y-%m-%d'), 'pre_dosing_time': pre_dosing_time,
            'dosing_date': dosing_date.strftime('%Y-%m-%d'), 'dosing_time': 'All Day',
            'follow_up_date': follow_up_date.strftime('%Y-%m-%d'), 'follow_up_time': follow_up_time,
            'booking_status': 'Active', 'notes': '', 'booking_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'cancellation_time': ''
        }
        
        # Append to Google Sheet first
        if sheet:
            row_to_save = [booking_data.get(col, "") for col in self.columns]
            sheet.append_row(row_to_save, value_input_option='USER_ENTERED')
        
        # Then update local state
        new_booking_df = pd.DataFrame([booking_data])
        self.bookings = pd.concat([self.bookings, new_booking_df], ignore_index=True)
        return True, "Booking successful"

    def cancel_booking(self, participant_id, reason):
        """Cancels a booking by updating its status."""
        if not sheet:
            return False, "Cannot cancel: No connection to Google Sheets"
        
        try:
            cell = sheet.find(participant_id)
            if not cell:
                return False, f"Could not find booking for participant ID: {participant_id}"

            row_number = cell.row
            headers = sheet.row_values(1)
            
            # Find column numbers for the fields to update
            status_col = headers.index('booking_status') + 1
            notes_col = headers.index('notes') + 1
            cancel_time_col = headers.index('cancellation_time') + 1
            
            # Update cells in the Google Sheet
            sheet.update_cell(row_number, status_col, 'Cancelled')
            sheet.update_cell(row_number, notes_col, f"Cancelled: {reason}")
            sheet.update_cell(row_number, cancel_time_col, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            
            return True, "Booking cancelled successfully"
        except Exception as e:
            return False, f"Error during cancellation: {e}"

# --- INITIALIZE SYSTEM ---
@st.cache_resource
def get_booking_system():
    return StudyBookingSystem()

booking_system = get_booking_system()

# --- UI: MAIN PAGE ---
st.title("Participant Booking System (DIPP Study)")
st.markdown("""
**Welcome to the DIPP Study booking system.** This tool will help you schedule your four required study visits.

- **Visit 1 (Baseline):** A 3-hour session for surveys and tasks.
- **Visit 2 (Pre-dosing):** A 5-hour session including an fMRI scan.
- **Visit 3 (Dosing Day):** An all-day session at the research center.
- **Visit 4 (Follow-up):** A final 5-hour session including an fMRI scan.

For Visits 2 and 4, you will select a start time for your **5-hour session block**.
""")
st.divider()

# --- UI: TABS ---
tab1, tab2 = st.tabs(["**🗓️ Book Appointment**", "**⚙️ Admin Panel**"])

with tab1:
    st.header("Book Your Appointments")
    
    st.info("Please complete all steps to secure your booking.", icon="👉")
    
    # --- Step 1: Participant Info ---
    with st.expander("**Step 1: Enter Your Information**", expanded=True):
        col1, col2 = st.columns(2)
        name = col1.text_input("Full Name")
        participant_id = col1.text_input("Participant ID")
        email = col2.text_input("Email Address")

    # --- Subsequent steps appear after info is entered ---
    if name and participant_id and email:
        with st.expander("**Step 2: Choose Your Schedule**", expanded=True):
            group = st.radio("Select your preferred dosing day group:", ["WEDNESDAY", "SATURDAY"], horizontal=True)
            dosing_dates = booking_system.get_dosing_dates(group)

            if not dosing_dates:
                st.warning("No available dosing dates for this group. Please contact the research team.")
            else:
                dosing_date = st.selectbox(f"Select an available **{group.capitalize()}** dosing date:", dosing_dates, format_func=lambda x: x.strftime("%A, %B %d, %Y"))
                
                # --- Calculate and display all dates based on selection ---
                pre_dosing_date = booking_system.get_pre_scan_date(dosing_date)
                follow_up_date = booking_system.get_follow_up_date(dosing_date, group)
                baseline_date = booking_system.get_baseline_date(dosing_date)
                baseline_available = booking_system.check_baseline_availability(baseline_date, group)
                baseline_time = "Daytime" if group == "WEDNESDAY" else "Evening"

                st.success(f"""
                **Your Generated Schedule:**
                - **Visit 1 (Baseline):** `{baseline_date.strftime('%A, %d %b %Y')}` (`{baseline_time}`)
                - **Visit 2 (Pre-dosing):** `{pre_dosing_date.strftime('%A, %d %b %Y')}`
                - **Visit 3 (Dosing Day):** `{dosing_date.strftime('%A, %d %b %Y')}` (`All Day`)
                - **Visit 4 (Follow-up):** `{follow_up_date.strftime('%A, %d %b %Y')}`
                """, icon="✅")

                if not baseline_available:
                    st.error("The Baseline slot for this schedule is already taken. Please select a different dosing date.", icon="❌")
                else:
                    with st.expander("**Step 3: Select Session Start Times**", expanded=True):
                        col1, col2 = st.columns(2)
                        available_times = booking_system.generate_daily_time_slots()
                        pre_dosing_time = col1.selectbox("Visit 2 (Pre-dosing) Start Time:", available_times, key="v2_time")
                        follow_up_time = col2.selectbox("Visit 4 (Follow-up) Start Time:", available_times, key="v4_time")
                    
                    st.divider()
                    st.header("Step 4: Confirm Your Booking")
                    if st.button("✅ Confirm and Book All Appointments", type="primary", use_container_width=True):
                        with st.spinner("Booking your appointments..."):
                            success, message = booking_system.book_participant(name, participant_id, email, group, baseline_date, pre_dosing_date, dosing_date, follow_up_date, pre_dosing_time, follow_up_time)
                            if success:
                                st.success("Booking Confirmed! Please write these dates in your calendar.")
                                st.balloons()
                            else:
                                st.error(f"Booking Failed: {message}")

with tab2:
    st.header("Admin Panel")
    password = st.text_input("Enter Admin Password", type="password")
    
    # Check password against Streamlit Secrets
    admin_password = st.secrets.get("admin_password", "admin123") # Default password if not in secrets

    if password == admin_password:
        st.success("Access Granted", icon="🔓")
        
        admin_tab1, admin_tab2 = st.tabs(["**View Bookings**", "**Cancel a Booking**"])
        
        with admin_tab1:
            st.subheader("All Participant Bookings")
            if st.button("🔄 Refresh Data from Google Sheets"):
                st.cache_resource.clear()
                st.rerun()

            bookings_df = booking_system.bookings
            if bookings_df.empty:
                st.info("No bookings found.")
            else:
                st.dataframe(bookings_df, use_container_width=True)

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
                    if not reason:
                        st.error("A reason for cancellation is required.")
                    else:
                        participant_id_to_cancel = options[selected_display]
                        with st.spinner("Cancelling booking..."):
                            success, message = booking_system.cancel_booking(participant_id_to_cancel, reason)
                            if success:
                                st.success(message)
                                st.cache_resource.clear() # Clear cache to reflect change
                            else:
                                st.error(message)

    elif password:
        st.error("Incorrect password. Access denied.", icon="🔒")
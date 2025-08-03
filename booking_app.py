import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
import gspread
from oauth2client.service_account import ServiceAccountCredentials

def check_secrets_configuration():
    """Check if secrets are properly configured and display appropriate messages"""
    if "google_sheets" not in st.secrets:
        st.sidebar.warning("⚠️ Google Sheets credentials not configured")
        st.sidebar.info("To enable Google Sheets integration, add credentials to Streamlit secrets")
        return False
        
    required_keys = ["type", "project_id", "private_key_id", "private_key", 
                     "client_email", "client_id"]
                     
    missing_keys = [key for key in required_keys if key not in st.secrets["google_sheets"]]
    
    if missing_keys:
        st.sidebar.warning(f"⚠️ Missing required credentials: {', '.join(missing_keys)}")
        return False
        
    return True

# Call this function right after defining it
secrets_configured = check_secrets_configuration()

# Add this at the top of your file, after the imports
def serialize_for_debug(obj):
    """Convert any object to a safe string for debugging"""
    if pd.isna(obj) or obj is None:
        return "NULL"
    elif isinstance(obj, (datetime, pd.Timestamp)):
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    elif isinstance(obj, (list, tuple, set)):
        return [serialize_for_debug(x) for x in obj]
    elif isinstance(obj, dict):
        return {str(k): serialize_for_debug(v) for k, v in obj.items()}
    elif isinstance(obj, pd.DataFrame):
        return f"DataFrame with {len(obj)} rows"
    else:
        return str(obj)

# App configuration and settings
st.set_page_config(
    page_title="DIPP Study Booking System",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Display app info in the sidebarr
st.sidebar.title("DIPP Booking System")
st.sidebar.caption("Version 1.2") # <<< CHANGED Version

# Caching Google Sheets connection to avoid reconnecting on each rerun
@st.cache_resource
def get_gsheet():
    """Connect to Google Sheets using credentials from st.secrets"""
    try:
        # Define the scope for Google Sheets API
        scope = ["https://spreadsheets.google.com/feeds", 
                 "https://www.googleapis.com/auth/drive"]
        
        # Check if Google Sheets credentials exist in secrets
        if "google_sheets" not in st.secrets:
            st.sidebar.error("Google Sheets credentials not found in secrets")
            st.sidebar.info("Running in local mode without Google Sheets connection")
            return None
            
        # Create credentials from the secrets dictionary
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(
                st.secrets["google_sheets"], scope)
        except Exception as cred_error:
            st.sidebar.error(f"Error creating credentials: {str(cred_error)}")
            return None
        
        # Authorize with Google
        try:
            client = gspread.authorize(creds)
        except Exception as auth_error:
            st.sidebar.error(f"Authorization failed: {str(auth_error)}")
            return None
        
        # Open the specific sheet - get name from secrets or use default
        sheet_name = st.secrets.get("sheet_name", "DIPP_Bookings")
        try:
            sheet = client.open(sheet_name).sheet1
        except Exception as sheet_error:
            st.sidebar.error(f"Could not open sheet '{sheet_name}': {str(sheet_error)}")
            return None
        
        # Quick verification that we can access the sheet
        try:
            # Just check if we can get a cell value
            sheet.cell(1, 1)
            st.sidebar.success("✅ Connected to Google Sheets")
            return sheet
        except Exception as access_error:
            st.sidebar.error(f"Could not access sheet data: {str(access_error)}")
            return None
            
    except Exception as e:
        st.sidebar.error(f"Error connecting to Google Sheets: {str(e)}")
        st.sidebar.info("Running in local mode without Google Sheets connection")
        return None

# Get the sheet connection
sheet = get_gsheet()


class StudyBookingSystem:
    def __init__(self):
        # Define expected columns (must match Google Sheet headers)
        self.columns = [
            'name', 'participant_id', 'email', 'group', 'baseline_date', 'baseline_time',
            'pre_dosing_date', 'pre_dosing_time', 'dosing_date', 'dosing_time',
            'follow_up_date', 'follow_up_time', 'booking_status', 'notes', 'booking_time',
            'cancellation_time'
        ]
        # Create empty dataframe in case loading fails
        self.bookings = pd.DataFrame(columns=self.columns)
        try:
            self._load_bookings_from_sheet()
        except Exception as e:
            st.error(f"Error initializing booking system: {str(e)}")
            st.info("The app will continue with an empty booking system. Some features may be limited.")

    def _load_bookings_from_sheet(self):
        """Super simplified booking loading function with better error handling"""
        try:
            if 'sheet' not in globals() or sheet is None:
                st.warning("No connection to Google Sheets. Using local storage only.")
                return
            
            all_cells = sheet.get_all_values()
            
            if not all_cells:
                sheet.update('A1', [self.columns])
                return
                
            headers = all_cells[0] if all_cells else []
            data = all_cells[1:] if len(all_cells) > 1 else []
            
            if data:
                self.bookings = pd.DataFrame(data, columns=headers)
                
        except Exception as e:
            st.warning(f"Could not read sheet data: {str(e)}")

    def get_all_bookings(self):
        """Return all bookings from the system"""
        return self.bookings

    def get_dosing_dates(self, group):
        """Get available dosing dates for the selected group"""
        start_date = datetime(2025, 5, 1).date()
        end_date = datetime(2025, 11, 29).date()
        target_day = 2 if group == 'WEDNESDAY' else 5

        dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
        valid_dates = [d for d in dates if d.weekday() == target_day]

        booked_dates = []
        if not self.bookings.empty and 'dosing_date' in self.bookings.columns:
            active = self.bookings[self.bookings['booking_status'] == 'Active']
            for date_str in active['dosing_date'].dropna():
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
        latest = dosing_date - timedelta(days=22)
        current = latest
        while current.weekday() != 0:
            current -= timedelta(days=1)
        return current

    # <<< CHANGED: New, simplified function to generate a static list of time slots.
    def generate_daily_time_slots(self):
        """Generates a list of all possible start times for a 5-hour session."""
        slots = []
        start_time = datetime.strptime("09:00", "%H:%M")
        # Latest start time is 5 PM to allow a 5-hour slot to end by 10 PM.
        end_time = datetime.strptime("17:00", "%H:%M")
        increment = timedelta(minutes=30)
        
        current_slot = start_time
        while current_slot <= end_time:
            slots.append(current_slot.strftime("%H:%M"))
            current_slot += increment
            
        return slots

    def check_baseline_availability(self, baseline_date, group):
        """Check if baseline date is available for the given group (Daytime/Evening slot)."""
        if self.bookings.empty:
            return True

        date_str = baseline_date.strftime('%Y-%m-%d')
        time_slot = "Daytime" if group == "WEDNESDAY" else "Evening"
        match = self.bookings[
            (self.bookings['booking_status'] == 'Active') &
            (self.bookings['baseline_date'] == date_str) &
            (self.bookings['baseline_time'] == time_slot)
        ]
        return match.empty

    def book_participant(self, name, participant_id, email, group, baseline_date, pre_dosing_date,
                         dosing_date, follow_up_date, pre_dosing_time, follow_up_time):
        """Book a participant for all four visits."""
        try:
            # Check for existing active bookings with this participant ID
            if not self.bookings.empty and participant_id in self.bookings[self.bookings['booking_status'] == 'Active']['participant_id'].values:
                return False, "Participant ID already has an active booking"

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

            new_booking_df = pd.DataFrame([booking_data])
            self.bookings = pd.concat([self.bookings, new_booking_df], ignore_index=True)

            if sheet is not None:
                # Convert DataFrame row to list of strings for gspread
                row_to_save = [str(val) if pd.notna(val) else "" for val in new_booking_df.iloc[0].values]
                sheet.append_row(row_to_save, value_input_option='RAW')
            
            return True, "Booking successful"
            
        except Exception as e:
            st.error(f"Error in booking process: {str(e)}")
            return False, f"Booking failed due to an error: {str(e)}"

    def cancel_booking(self, participant_id, reason):
        """Cancel an existing booking."""
        try:
            if sheet is None:
                return False, "Cannot cancel: No connection to Google Sheets"
            
            # Find in local dataframe
            idx = self.bookings[(self.bookings['participant_id'] == participant_id) & (self.bookings['booking_status'] == 'Active')].index
            if idx.empty:
                return False, f"Could not find active booking for participant ID: {participant_id}"

            # Find in Google Sheet
            cell = sheet.find(participant_id)
            if not cell:
                return False, f"Could not find booking in sheet for participant ID: {participant_id}"
            row_number = cell.row

            # Update local dataframe
            self.bookings.loc[idx, 'booking_status'] = 'Cancelled'
            self.bookings.loc[idx, 'notes'] = f"Cancelled: {reason}"
            self.bookings.loc[idx, 'cancellation_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Update Google Sheet
            # Find column indexes for the fields we need to update
            headers = sheet.row_values(1)
            status_col = headers.index('booking_status') + 1
            notes_col = headers.index('notes') + 1
            cancel_time_col = headers.index('cancellation_time') + 1

            sheet.update_cell(row_number, status_col, 'Cancelled')
            sheet.update_cell(row_number, notes_col, f"Cancelled: {reason}")
            sheet.update_cell(row_number, cancel_time_col, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

            return True, "Booking cancelled successfully"
                
        except Exception as e:
            return False, f"Error in cancellation process: {str(e)}"

# Initialize the booking system
@st.cache_resource
def get_booking_system():
    return StudyBookingSystem()

booking_system = get_booking_system()

# --- UI STARTS HERE ---
st.title("Participant Booking System (DIPP Study)")

st.markdown("""
**About the DIPP study visits**

The DIPP study requires participants to attend four separate visits:

1.  **Baseline Visit (Visit 1)**: About 3 weeks before your dosing day, you'll come in for your first baseline visit to do surveys and computer tasks (about 3 hours).
2.  **Pre-dosing Visit (Visit 2)**: One day before your dosing, you'll need to come in for about **5 hours** to complete surveys, computer tasks, and have an fMRI movie scan.
3.  **Dosing Day (Visit 3)**: This is the main visit where you'll spend all day at the center.
4.  **Follow-up Visit (Visit 4)**: About 2 weeks after your dosing day, you'll come in for about **5 hours** to complete surveys, computer tasks, and have an fMRI movie scan.

**Note about time slots**:
* For Visits 2 and 4, you will select your preferred start time below. This will schedule your **5-hour block** for that day.
* For Visit 1 (Baseline), the time is fixed to either 'Daytime' or 'Evening' depending on your group.

If you cannot attend any of the available slots, please contact the DIPP Research Team directly (dipp-project@ucl.ac.uk).
---
""")

# Tabs for booking and admin
tab1, tab2 = st.tabs(["Book Appointment", "Admin Panel"])

with tab1:
    st.header("Book New Appointment")
    
    # Step 1: Participant Information
    st.subheader("Step 1: Enter Your Information")
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Full Name")
        participant_id = st.text_input("Participant ID")
    with col2:
        email = st.text_input("Email Address")
    
    # Subsequent steps only appear after initial info is entered
    if name and participant_id and email:
        st.subheader("Step 2: Select Dosing Group")
        group = st.radio("Which group would you prefer?", ["WEDNESDAY", "SATURDAY"])
        
        if group:
            st.subheader(f"Step 3: Select {group.capitalize()} Dosing Date")
            dosing_dates = booking_system.get_dosing_dates(group)
            
            if not dosing_dates:
                st.warning("No available dosing dates for this group.")
                dosing_date = None
            else:
                dosing_date = st.selectbox(
                    f"Available {group.capitalize()} Dosing Dates (Visit 3, All Day)", 
                    options=dosing_dates,
                    format_func=lambda x: x.strftime("%A, %B %d, %Y")
                )
        
            if dosing_date:
                pre_dosing_date = booking_system.get_pre_scan_date(dosing_date)
                follow_up_date = booking_system.get_follow_up_date(dosing_date, group)
                baseline_date = booking_system.get_baseline_date(dosing_date)
                baseline_available = booking_system.check_baseline_availability(baseline_date, group)
                
                st.subheader("Step 4: Confirm Your Visit Schedule")
                
                # Visit 1: Baseline
                st.markdown("#### Visit 1: Baseline")
                if not baseline_available:
                    st.warning("⚠️ This baseline slot is already booked. Please select a different dosing date.")
                baseline_time = "Daytime" if group == "WEDNESDAY" else "Evening"
                st.markdown(f"**Date**: {baseline_date.strftime('%A, %B %d, %Y')} at **Time**: {baseline_time}")

                # <<< CHANGED: Visit 2 UI uses the new simple function
                st.markdown("#### Visit 2: Pre-dosing")
                st.markdown(f"**Date**: {pre_dosing_date.strftime('%A, %B %d, %Y')}")
                available_times = booking_system.generate_daily_time_slots()
                pre_dosing_time = st.selectbox(
                    "Select a start time for your 5-hour session", 
                    options=available_times,
                    key="pre_dosing_time"
                )

                # Visit 3: Dosing Day
                st.markdown("#### Visit 3: Dosing Day")
                st.markdown(f"**Date**: {dosing_date.strftime('%A, %B %d, %Y')} at **Time**: All Day")

                # <<< CHANGED: Visit 4 UI uses the new simple function
                st.markdown("#### Visit 4: Follow-up")
                st.markdown(f"**Date**: {follow_up_date.strftime('%A, %B %d, %Y')}")
                follow_up_time = st.selectbox(
                    "Select a start time for your 5-hour session", 
                    options=available_times,
                    key="follow_up_time"
                )
                
                st.subheader("Step 5: Confirm Booking")
                
                can_book = baseline_available
                if not can_book:
                    st.error("Cannot proceed. The Baseline visit slot is already taken. Please select a different Dosing Date.")
                
                if st.button("Book Appointments", disabled=not can_book):
                    success, message = booking_system.book_participant(
                        name, participant_id, email, group, 
                        baseline_date, pre_dosing_date, dosing_date, follow_up_date,
                        pre_dosing_time, follow_up_time
                    )
                    
                    if success:
                        st.success("✅ Booking Confirmed!")
                        st.balloons()
                        # Display confirmation summary
                        st.subheader("Your Confirmed Visit Schedule:")
                        st.markdown(f"""
                        - **Visit 1 (Baseline):** `{baseline_date.strftime('%A, %d %b %Y')}` at `{baseline_time}`
                        - **Visit 2 (Pre-dosing):** `{pre_dosing_date.strftime('%A, %d %b %Y')}` starting at `{pre_dosing_time}`
                        - **Visit 3 (Dosing Day):** `{dosing_date.strftime('%A, %d %b %Y')}` at `All Day`
                        - **Visit 4 (Follow-up):** `{follow_up_date.strftime('%A, %d %b %Y')}` starting at `{follow_up_time}`
                        """)
                        st.info("Please write these dates down. A member of the research team will also be in touch.")
                    else:
                        st.error(f"❌ Booking Failed: {message}")

with tab2:
    # Admin Panel code remains the same as it was not the source of the error.
    # You can paste your existing admin panel code here.
    st.header("Admin Panel")
    admin_password = st.text_input("Admin Password", type="password", key="admin_pw")
    
    if admin_password == st.secrets.get("admin_password", "default_password"): # Replace "default_password" or set in secrets
        admin_tabs = st.tabs(["View Bookings", "Cancel Booking"])
        
        with admin_tabs[0]:
            st.subheader("All Bookings")
            if st.button("Refresh Bookings"):
                st.cache_resource.clear()
                st.rerun()
            
            bookings_df = booking_system.get_all_bookings()
            if bookings_df.empty:
                st.info("No bookings found.")
            else:
                st.dataframe(bookings_df)
        
        with admin_tabs[1]:
            st.subheader("Cancel a Booking")
            active_bookings = booking_system.get_all_bookings()
            active_bookings = active_bookings[active_bookings['booking_status'] == 'Active']

            if active_bookings.empty:
                st.info("No active bookings to cancel.")
            else:
                options = {f"{row['participant_id']} - {row['name']}": row['participant_id'] for _, row in active_bookings.iterrows()}
                selected_display = st.selectbox("Select booking to cancel", options.keys())
                reason = st.text_input("Reason for cancellation")

                if st.button("Cancel Selected Booking"):
                    if not reason:
                        st.error("A reason for cancellation is required.")
                    else:
                        participant_id_to_cancel = options[selected_display]
                        success, message = booking_system.cancel_booking(participant_id_to_cancel, reason)
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)

    elif admin_password:
        st.error("Incorrect password.")
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials


# App configuration and settings
st.set_page_config(
    page_title="DIPP Study Booking System",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Display app info in the sidebar
st.sidebar.title("DIPP Booking System")
st.sidebar.caption("Version 1.0")

# Caching Google Sheets connection to avoid reconnecting on each rerun
@st.cache_resource
def get_gsheet():
    """Connect to Google Sheets using credentials from st.secrets"""
    try:
        # Define the scope for Google Sheets API
        scope = ["https://spreadsheets.google.com/feeds", 
                "https://www.googleapis.com/auth/drive"]
        
        # Get credentials from secrets
        if "google_sheets" not in st.secrets:
            st.sidebar.error("Google Sheets credentials not found in secrets")
            return None
            
        # Create credentials from the secrets dictionary
        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            st.secrets["google_sheets"], scope)
        
        # Authorize with Google
        client = gspread.authorize(creds)
        
        # Open the specific sheet - get name from secrets or use default
        sheet_name = st.secrets.get("sheet_name", "DIPP_Bookings")
        sheet = client.open(sheet_name).sheet1
        
        # Verify connection by getting the headers
        headers = sheet.row_values(1)
        
        # If sheet is empty, initialize with headers
        if not headers:
            sheet.append_row([
                'name', 'participant_id', 'email', 'group', 'baseline_date', 
                'baseline_time', 'pre_dosing_date', 'pre_dosing_time', 
                'dosing_date', 'dosing_time', 'follow_up_date', 'follow_up_time', 
                'booking_status', 'notes', 'booking_time', 'cancellation_time'
            ])
            st.sidebar.info("Initialized sheet with headers")
        
        st.sidebar.success("✅ Connected to Google Sheets")
        return sheet
    except Exception as e:
        st.sidebar.error(f"Error connecting to Google Sheets: {str(e)}")
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
        self._load_bookings_from_sheet()

    def _load_bookings_from_sheet(self):
        """Load data from Google Sheets"""
        try:
            if sheet is None:
                self.bookings = pd.DataFrame(columns=self.columns)
                return
                
            # Get all records from the sheet
            records = sheet.get_all_records()
            self.bookings = pd.DataFrame(records)

            # If sheet is empty (besides headers)
            if self.bookings.empty:
                self.bookings = pd.DataFrame(columns=self.columns)
            else:
                # Ensure all expected columns exist
                for col in self.columns:
                    if col not in self.bookings.columns:
                        self.bookings[col] = None
                        
        except Exception as e:
            st.error(f"Error loading bookings from Google Sheets: {str(e)}")
            self.bookings = pd.DataFrame(columns=self.columns)

    def _save_latest_booking_to_sheet(self):
        """Append the latest booking row to Google Sheets"""
        try:
            if sheet is None:
                st.error("Cannot save booking: No connection to Google Sheets")
                return False
                
            latest = self.bookings.iloc[-1]
            
            # Convert any datetime objects to strings before saving
            row_to_save = []
            for col in self.columns:
                val = latest.get(col, "")
                # Handle any conversion needed
                if pd.isna(val) or val is None:
                    val = ""
                row_to_save.append(val)
            
            # Append to the sheet
            sheet.append_row(row_to_save, value_input_option='USER_ENTERED')
            return True
            
        except Exception as e:
            st.error(f"Error saving booking to Google Sheets: {str(e)}")
            return False

    def get_all_bookings(self):
        """Return all bookings from the system"""
        return self.bookings

    def get_dosing_dates(self, group):
        """Get available dosing dates for the selected group"""
        start_date = datetime(2025, 5, 1).date()
        end_date = datetime(2025, 10, 31).date()
        target_day = 2 if group == 'WEDNESDAY' else 5  # 2=Wednesday, 5=Saturday

        # Generate all possible dates in the range
        dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
        valid_dates = [d for d in dates if d.weekday() == target_day]

        # Remove dates that are already booked
        booked_dates = []
        if not self.bookings.empty:
            active = self.bookings[self.bookings['booking_status'] == 'Active']
            if not active.empty and 'dosing_date' in active.columns:
                # Handle potential formatting issues
                for date_str in active['dosing_date'].dropna():
                    try:
                        booked_dates.append(datetime.strptime(date_str, '%Y-%m-%d').date())
                    except (ValueError, TypeError):
                        pass  # Skip invalid dates

        return [d for d in valid_dates if d not in booked_dates]

    def get_pre_scan_date(self, dosing_date):
        """Calculate pre-dosing date (day before dosing)"""
        return dosing_date - timedelta(days=1)

    def get_follow_up_date(self, dosing_date, group):
        """Calculate follow-up date (about 14 days after dosing)"""
        follow_up = dosing_date + timedelta(days=14)
        target_day = 3 if group == 'WEDNESDAY' else 6  # 3=Thursday, 6=Sunday
        
        # Adjust to nearest target day
        while follow_up.weekday() != target_day:
            follow_up += timedelta(days=1)
        return follow_up

    def get_baseline_date(self, dosing_date):
        """Calculate baseline date (at least 22 days before dosing, on a Monday)"""
        earliest = dosing_date - timedelta(days=60)
        latest = dosing_date - timedelta(days=22)
        current = latest
        
        # Find the nearest Monday
        while current.weekday() != 0:  # 0=Monday
            current -= timedelta(days=1)
            
        return current if current >= earliest else None

    def get_available_pre_dosing_times(self, pre_dosing_date, group):
        """Get available time slots for pre-dosing visit"""
        if self.bookings.empty:
            return ["Daytime", "Evening"]

        date_str = pre_dosing_date.strftime('%Y-%m-%d')
        booked = self.bookings[
            (self.bookings['booking_status'] == 'Active') &
            (self.bookings['pre_dosing_date'] == date_str)
        ]
        taken = booked['pre_dosing_time'].tolist() if not booked.empty else []
        return [t for t in ["Daytime", "Evening"] if t not in taken]

    def get_available_follow_up_times(self, follow_up_date, group):
        """Get available time slots for follow-up visit"""
        if self.bookings.empty:
            return ["Daytime", "Evening"]

        date_str = follow_up_date.strftime('%Y-%m-%d')
        booked = self.bookings[
            (self.bookings['booking_status'] == 'Active') &
            (self.bookings['follow_up_date'] == date_str)
        ]
        taken = booked['follow_up_time'].tolist() if not booked.empty else []
        return [t for t in ["Daytime", "Evening"] if t not in taken]

    def check_baseline_availability(self, baseline_date, group):
        """Check if baseline date is available for the given group"""
        if self.bookings.empty:
            return True

        date_str = baseline_date.strftime('%Y-%m-%d')
        time = "Daytime" if group == "WEDNESDAY" else "Evening"
        match = self.bookings[
            (self.bookings['booking_status'] == 'Active') &
            (self.bookings['baseline_date'] == date_str) &
            (self.bookings['baseline_time'] == time)
        ]
        return match.empty

    def book_participant(self, name, participant_id, email, group, baseline_date, pre_dosing_date,
                         dosing_date, follow_up_date, pre_dosing_time, follow_up_time):
        """Book a participant for all four visits"""
        # Validate the booking dates
        if not self._validate_booking(baseline_date, pre_dosing_date, dosing_date, follow_up_date, group):
            return False, "Invalid booking dates. Please try again with different dates."

        # Check for existing active bookings with this participant ID
        if not self.bookings.empty and 'participant_id' in self.bookings.columns:
            active_bookings = self.bookings[self.bookings['booking_status'] == 'Active']
            if not active_bookings.empty and participant_id in active_bookings['participant_id'].values:
                return False, "Participant ID already has an active booking"

        # Set baseline time based on group
        baseline_time = "Daytime" if group == "WEDNESDAY" else "Evening"

        # Create new booking record
        new_booking = pd.DataFrame([{
            'name': name,
            'participant_id': participant_id,
            'email': email,
            'group': group,
            'baseline_date': baseline_date.strftime('%Y-%m-%d'),
            'baseline_time': baseline_time,
            'pre_dosing_date': pre_dosing_date.strftime('%Y-%m-%d'),
            'pre_dosing_time': pre_dosing_time,
            'dosing_date': dosing_date.strftime('%Y-%m-%d'),
            'dosing_time': 'All Day',
            'follow_up_date': follow_up_date.strftime('%Y-%m-%d'),
            'follow_up_time': follow_up_time,
            'booking_status': 'Active',
            'notes': '',
            'booking_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'cancellation_time': ''
        }])

        # Add to in-memory dataframe
        self.bookings = pd.concat([self.bookings, new_booking], ignore_index=True)
        
        # Save to Google Sheets
        if not self._save_latest_booking_to_sheet():
            return False, "Booking created but failed to save to Google Sheets"
            
        return True, "Booking successful"

    def cancel_booking(self, participant_id, reason):
        """Cancel an existing booking"""
        try:
            if sheet is None:
                return False, "Cannot cancel booking: No connection to Google Sheets"
                
            # Find row number of the participant
            cell = sheet.find(participant_id)
            if not cell:
                return False, f"Could not find participant with ID: {participant_id}"
                
            row_number = cell.row

            # Get current row values
            current_values = sheet.row_values(row_number)

            # Get headers
            headers = sheet.row_values(1)

            # Create a dict of current row values
            data_dict = dict(zip(headers, current_values))

            # Update fields
            data_dict["booking_status"] = "Cancelled"
            data_dict["notes"] = f"Cancelled: {reason}"
            data_dict["cancellation_time"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Ensure all expected columns exist
            updated_row = [data_dict.get(col, "") for col in headers]

            # Update the full row in Google Sheets
            sheet.update(f"A{row_number}:P{row_number}", [updated_row])

            # Also update in memory
            idx = self.bookings[self.bookings['participant_id'] == participant_id].index
            if not idx.empty:
                self.bookings.loc[idx, 'booking_status'] = 'Cancelled'
                self.bookings.loc[idx, 'notes'] = data_dict["notes"]
                self.bookings.loc[idx, 'cancellation_time'] = data_dict["cancellation_time"]

            return True, "Booking cancelled successfully"

        except Exception as e:
            return False, f"Error cancelling booking: {str(e)}"

    def reset_all_bookings(self):
        """Clear all bookings from Google Sheets - for admin use only"""
        try:
            if sheet is None:
                return False, "Cannot reset bookings: No connection to Google Sheets"
                
            # Clear all rows in the sheet except the header row
            if sheet.row_count > 1:
                sheet.delete_rows(2, sheet.row_count)  # Delete from row 2 to the end
            
            # Reset the in-memory dataframe
            self.bookings = pd.DataFrame(columns=self.columns)
            
            return True, "All bookings have been reset"
        except Exception as e:
            return False, f"Error resetting bookings: {str(e)}"

    def _validate_booking(self, baseline, pre_dosing, dosing, follow_up, group):
        """Validate that all booking dates follow study requirements"""
        # Check dosing day is correct for the group
        if group == 'WEDNESDAY' and dosing.weekday() != 2:
            return False
        if group == 'SATURDAY' and dosing.weekday() != 5:
            return False
            
        # Check pre-dosing is 1 day before dosing
        if (dosing - pre_dosing).days != 1:
            return False
            
        # Check baseline is at least 22 days before and on Monday
        if (dosing - baseline).days < 22 or baseline.weekday() != 0:
            return False
            
        # Check follow-up is on correct day based on group
        if group == 'WEDNESDAY' and follow_up.weekday() != 3:
            return False
        if group == 'SATURDAY' and follow_up.weekday() != 6:
            return False
            
        return True


# Initialize the booking system (cached to prevent reloading on each interaction)
@st.cache_resource
def get_booking_system():
    return StudyBookingSystem()

booking_system = get_booking_system()


# App title
st.title("Participant Booking System (DIPP Study)")


# Study information
st.markdown("""
**About the DIPP study visits**

The DIPP study requires participants to attend four separate visits:

1. **Baseline Visit (Visit 1)**: About 3 weeks before your dosing day, you'll come in for your first baseline visit to do surveys and computer tasks (about 3 hours).
   **Location: 26 Bedford Way, London**

2. **Pre-dosing Visit (Visit 2)**: One day before your dosing, you'll need to come in for about 5 hours to complete surveys, computer tasks, and have an fMRI movie scan. You can choose either daytime or evening.
   **Location: 26 Bedford Way, London**

3. **Dosing Day (Visit 3)**: This is the main visit where you'll spend all day at the center. You can choose either a Wednesday or Saturday.
   **Location: 1-19 Torrington Place, London**

4. **Follow-up Visit (Visit 4)**: About 2 weeks after your dosing day, you'll come in for about 5 hours to complete surveys, computer tasks, and have an fMRI movie scan. You can choose either daytime or evening.
   **Location: 26 Bedford Way, London**

**Important**: Between Visit 1 and Visit 2, you'll complete the 21-day preparation programme using our web app. This includes daily morning practices, weekly activities, and submitting a brief voice note twice a day (we'll guide you through the whole process).

**Note about time slots**:
* **Daytime**: Generally between 9:00 AM - 5:00 PM
* **Evening**: Generally between 5:00 PM - 10:00 PM

The research team will contact you to arrange specific times within these blocks. You can use the booking system below to book your slot. Once you have booked a slot, it will no longer be available for other people to book. If you cannot attend any of the available slots, please contact the DIPP Research Team directly (dipp-project@ucl.ac.uk).

---
            
## Our Scheduling System

We have two scheduling groups:

### Wednesday Dosing Group:
- **Dosing Day**: Wednesday (all day)
- **Pre-dosing Visit**: Tuesday (1 day before), choose daytime or evening
- **Baseline Visit**: Monday (at least 22 days before dosing), daytime only
- **Follow-up Visit**: Thursday (about 2 weeks after dosing), choose daytime or evening

### Saturday Dosing Group:
- **Dosing Day**: Saturday (all day)
- **Pre-dosing Visit**: Friday (1 day before), choose daytime or evening
- **Baseline Visit**: Monday (at least 22 days before dosing), evening only
- **Follow-up Visit**: Sunday (about 2 weeks after dosing), choose daytime or evening

Please select your preferred dosing group and date below.
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
    
    # Step 2: Group Selection
    if name and participant_id and email:
        st.subheader("Step 2: Select Dosing Group")
        group = st.radio("Which group would you prefer?", ["WEDNESDAY", "SATURDAY"])
        
        # Step 3: Dosing Date Selection (depends on group)
        if group:
            st.subheader(f"Step 3: Select {group.capitalize()} Dosing Date")
            dosing_dates = booking_system.get_dosing_dates(group)
            
            if not dosing_dates:
                st.warning("No available dosing dates for this group. All dates may be booked.")
                dosing_date = None
            else:
                dosing_date = st.selectbox(
                    f"Available {group.capitalize()} Dosing Dates (Visit 3, All Day)", 
                    options=dosing_dates,
                    format_func=lambda x: x.strftime("%A, %B %d, %Y")
                )
        
            # Step 4: Show all visit details (depends on dosing date)
            if dosing_date:
                # Calculate other visit dates
                pre_dosing_date = booking_system.get_pre_scan_date(dosing_date)
                follow_up_date = booking_system.get_follow_up_date(dosing_date, group)
                baseline_date = booking_system.get_baseline_date(dosing_date)
                
                # Check baseline availability
                baseline_available = booking_system.check_baseline_availability(baseline_date, group)
                
                # Display visit information
                st.subheader("Step 4: Confirm Your Visit Schedule")
                
                # Visit 1: Baseline
                st.markdown("#### Visit 1: Baseline")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"**Date**: {baseline_date.strftime('%A, %B %d, %Y')}")
                with col2:
                    baseline_time = "Daytime" if group == "WEDNESDAY" else "Evening"
                    st.markdown(f"**Time**: {baseline_time}")
                with col3:
                    st.markdown("**Location**: 26 Bedford Way")
                
                if not baseline_available:
                    st.warning(f"⚠️ This baseline slot is already booked. Please select a different dosing date.")
                
                # Visit 2: Pre-dosing
                st.markdown("#### Visit 2: Pre-dosing")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"**Date**: {pre_dosing_date.strftime('%A, %B %d, %Y')}")
                with col2:
                    available_pre_dosing_times = booking_system.get_available_pre_dosing_times(pre_dosing_date, group)
                    if not available_pre_dosing_times:
                        st.warning("⚠️ No available time slots for this pre-dosing date.")
                        pre_dosing_time = None
                    else:
                        pre_dosing_time = st.radio(
                            "Select Time for Pre-dosing Visit", 
                            options=available_pre_dosing_times,
                            key="pre_dosing_time"
                        )
                with col3:
                    st.markdown("**Location**: 26 Bedford Way")
                
                # Visit 3: Dosing Day
                st.markdown("#### Visit 3: Dosing Day")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"**Date**: {dosing_date.strftime('%A, %B %d, %Y')}")
                with col2:
                    st.markdown("**Time**: All Day")
                with col3:
                    st.markdown("**Location**: 1-19 Torrington Place")
                
                # Visit 4: Follow-up
                st.markdown("#### Visit 4: Follow-up")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"**Date**: {follow_up_date.strftime('%A, %B %d, %Y')}")
                with col2:
                    available_follow_up_times = booking_system.get_available_follow_up_times(follow_up_date, group)
                    if not available_follow_up_times:
                        st.warning("⚠️ No available time slots for this follow-up date.")
                        follow_up_time = None
                    else:
                        follow_up_time = st.radio(
                            "Select Time for Follow-up Visit", 
                            options=available_follow_up_times,
                            key="follow_up_time"
                        )
                with col3:
                    st.markdown("**Location**: 26 Bedford Way")
                
                # Step 5: Submit booking
                st.subheader("Step 5: Confirm Booking")
                
                # Remind about the 21-day preparation period
                st.info("**Remember**: Between Visit 1 (Baseline) and Visit 2 (Pre-dosing), you'll begin your 21-day preparation period. This includes daily morning practices and submitting voice notes twice a day.")
                
                # Determine if we can proceed with booking
                can_book = (
                    baseline_available and 
                    pre_dosing_time is not None and 
                    follow_up_time is not None
                )
                
                if not can_book:
                    st.error("Cannot proceed with booking due to unavailable time slots. Please select a different dosing date.")
                
                if st.button("Book Appointments", disabled=not can_book):
                    success, message = booking_system.book_participant(
                        name, participant_id, email, group, 
                        baseline_date, pre_dosing_date, dosing_date, follow_up_date,
                        pre_dosing_time, follow_up_time
                    )
                    
                    if success:
                        st.success("✅ Booking Confirmed!")
                        
                        st.markdown(f"**Name:** {name}")
                        st.markdown(f"**Participant ID:** {participant_id}")
                        st.markdown(f"**Email:** {email}")
                        st.markdown(f"**Group:** {group}")
                        
                        st.subheader("Your Visit Schedule:")
                        
                        # Create a nice table for the schedule
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.markdown("**Visit**")
                            st.markdown("Visit 1 (Baseline)")
                            st.markdown("Visit 2 (Pre-dosing)")
                            st.markdown("Visit 3 (Dosing)")
                            st.markdown("Visit 4 (Follow-up)")
                        with col2:
                            st.markdown("**Date**")
                            st.markdown(f"{baseline_date.strftime('%A, %B %d, %Y')}")
                            st.markdown(f"{pre_dosing_date.strftime('%A, %B %d, %Y')}")
                            st.markdown(f"{dosing_date.strftime('%A, %B %d, %Y')}")
                            st.markdown(f"{follow_up_date.strftime('%A, %B %d, %Y')}")
                        with col3:
                            st.markdown("**Time**")
                            baseline_time = "Daytime" if group == "WEDNESDAY" else "Evening"
                            st.markdown(f"{baseline_time}")
                            st.markdown(f"{pre_dosing_time}")
                            st.markdown("All Day")
                            st.markdown(f"{follow_up_time}")
                        with col4:
                            st.markdown("**Location**")
                            st.markdown("26 Bedford Way")
                            st.markdown("26 Bedford Way")
                            st.markdown("1-19 Torrington Place")
                            st.markdown("26 Bedford Way")
                        
                        # Add manual planner reminder message
                        st.markdown("---")
                        st.info("⚠️ **Important**: Please write down these appointments in your planner or calendar. A member of the DIPP team will contact you to arrange the specific times within these blocks.")
                        
                        # Offer printable schedule option
                        st.markdown("""
                        ### 📝 Your DIPP Study Schedule
                        
                        Please copy or write down the following information in your personal calendar:
                        
                        **Visit 1 (Baseline)**  
                        Date: {baseline_date}  
                        Time: {baseline_time}  
                        Location: 26 Bedford Way, London
                        
                        **Visit 2 (Pre-dosing)**  
                        Date: {pre_dosing_date}  
                        Time: {pre_dosing_time}  
                        Location: 26 Bedford Way, London
                        
                        **Visit 3 (Dosing Day)**  
                        Date: {dosing_date}  
                        Time: All Day  
                        Location: 1-19 Torrington Place, London
                        
                        **Visit 4 (Follow-up)**  
                        Date: {follow_up_date}  
                        Time: {follow_up_time}  
                        Location: 26 Bedford Way, London
                        
                        **Note**: The DIPP research team will contact you to confirm the exact time within these blocks.
                        """.format(
                            baseline_date=baseline_date.strftime("%A, %B %d, %Y"),
                            baseline_time=baseline_time,
                            pre_dosing_date=pre_dosing_date.strftime("%A, %B %d, %Y"),
                            pre_dosing_time=pre_dosing_time,
                            dosing_date=dosing_date.strftime("%A, %B %d, %Y"),
                            follow_up_date=follow_up_date.strftime("%A, %B %d, %Y"),
                            follow_up_time=follow_up_time
                        ))
                        
                    else:
                        st.error(f"❌ Booking Failed: {message}")
    else:
        st.info("Please enter your name, participant ID, and email address to continue.")

with tab2:
    st.header("Admin Panel")
    
    # Password protection for admin
    admin_password = st.text_input("Admin Password", type="password")
    
    if admin_password == st.secrets.get("admin_password", ""):
        admin_tabs = st.tabs(["View Bookings", "Cancel Booking", "System Management"])
        
        with admin_tabs[0]:
            st.subheader("All Bookings")
            
            # Filter options
            st.markdown("#### Filter Options")
            col1, col2 = st.columns(2)
            with col1:
                status_filter = st.multiselect("Booking Status", 
                                               options=["Active", "Cancelled", "All"], 
                                               default=["Active"])
            with col2:
                group_filter = st.multiselect("Group", 
                                              options=["WEDNESDAY", "SATURDAY", "All"], 
                                              default=["All"])
            
            if st.button("Refresh Bookings"):
                booking_system._load_bookings_from_sheet()
                st.success("Bookings refreshed from Google Sheets")
            
            # Get and filter bookings
            bookings = booking_system.get_all_bookings()
            
            if len(bookings) == 0:
                st.info("No bookings yet")
            else:
                # Apply filters
                filtered_bookings = bookings.copy()
                
                if "All" not in status_filter:
                    filtered_bookings = filtered_bookings[filtered_bookings['booking_status'].isin(status_filter)]
                
                if "All" not in group_filter:
                    filtered_bookings = filtered_bookings[filtered_bookings['group'].isin(group_filter)]
                
                # Display bookings
                st.dataframe(filtered_bookings, use_container_width=True)
                
                # Export option
                if not filtered_bookings.empty:
                    csv = filtered_bookings.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "Download Bookings as CSV",
                        csv,
                        "study_bookings.csv",
                        "text/csv",
                        key='download-csv'
                    )
        
        with admin_tabs[1]:
            st.subheader("Cancel a Booking")
            
            # Get active bookings
            bookings = booking_system.get_all_bookings()
            active_bookings = bookings[bookings['booking_status'] == 'Active'] if not bookings.empty else pd.DataFrame()
            
            if active_bookings.empty:
                st.info("No active bookings to cancel")
            else:
                # Create options for selection
                booking_options = {f"{row['participant_id']} - {row['name']} - {row['dosing_date']}": row['participant_id'] 
                                  for _, row in active_bookings.iterrows()}
                
                # Select booking to cancel
                selected_booking = st.selectbox("Select Booking to Cancel", options=list(booking_options.keys()))
                cancellation_reason = st.text_area("Reason for Cancellation", height=100)
                
                if st.button("Cancel Selected Booking"):
                    if not cancellation_reason:
                        st.error("Please provide a reason for cancellation")
                    else:
                        participant_id = booking_options[selected_booking]
                        success, message = booking_system.cancel_booking(participant_id, cancellation_reason)
                        
                        if success:
                            st.success(f"✅ {message}")
                            # Refresh the bookings after cancellation
                            booking_system._load_bookings_from_sheet()
                        else:
                            st.error(f"❌ {message}")
        
        with admin_tabs[2]:
            st.subheader("System Management")
            
            # Reset all bookings (for piloting)
            st.markdown("#### Reset All Bookings")
            st.warning("⚠️ This will remove all bookings from the system. Use only for testing/piloting.")
            
            confirm_reset = st.checkbox("I understand this will delete all bookings")
            
            if st.button("Reset All Bookings", disabled=not confirm_reset):
                success, message = booking_system.reset_all_bookings()
                if success:
                    st.success(f"✅ {message}")
                else:
                    st.error(f"❌ {message}")
                    
            # View connection status
            st.markdown("#### Google Sheets Connection Status")
            
            if sheet:
                st.success("✅ Connected to Google Sheets")
                # Show some sheet info
                try:
                    st.write(f"Sheet name: {st.secrets.get('sheet_name', 'DIPP_Bookings')}")
                    st.write(f"Total rows: {sheet.row_count}")
                    st.write(f"Headers: {sheet.row_values(1)}")
                except Exception as e:
                    st.error(f"Error getting sheet details: {str(e)}")
            else:
                st.error("❌ Not connected to Google Sheets")
    
    elif admin_password:
        st.error("Incorrect password")
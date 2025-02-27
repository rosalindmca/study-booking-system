import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from ics import Calendar, Event
import pytz

# Set page config
st.set_page_config(page_title="Study Visit Booking System", layout="wide")

# Create a class to handle the booking logic
class StudyBookingSystem:
    def __init__(self):
        self.bookings_file = "study_bookings.json"
        
        # Define required columns for our system
        required_columns = [
            'name', 'participant_id', 'email', 'group', 'baseline_date', 
            'pre_dosing_date', 'dosing_date', 'follow_up_date',
            'booking_status', 'notes'
        ]
        
        # Load existing bookings if file exists
        if os.path.exists(self.bookings_file):
            try:
                with open(self.bookings_file, 'r') as f:
                    data = json.load(f)
                    # Create DataFrame from the data
                    self.bookings = pd.DataFrame(data)
                    
                    # Add any missing columns with default values
                    for column in required_columns:
                        if column not in self.bookings.columns:
                            if column == 'booking_status':
                                self.bookings[column] = 'Active'  # Default status for existing bookings
                            elif column == 'notes':
                                self.bookings[column] = ''
                            else:
                                self.bookings[column] = None
            except:
                self.bookings = pd.DataFrame(columns=required_columns)
        else:
            self.bookings = pd.DataFrame(columns=required_columns)
    
    def get_dosing_dates(self, group):
        """Generate all possible dosing dates between May-June 2025"""
        start_date = datetime(2025, 5, 1).date()
        end_date = datetime(2025, 6, 30).date()
        
        dates = []
        current = start_date
        
        # Wednesday (2) or Saturday (5)
        target_day = 2 if group == 'WEDNESDAY' else 5
        
        while current <= end_date:
            if current.weekday() == target_day:
                dates.append(current)
            current += timedelta(days=1)
        
        # Filter out already booked dates (with active status)
        # Ensure only one booking per dosing date
        booked_dates = []
        if 'dosing_date' in self.bookings.columns and not self.bookings.empty:
            active_bookings = self.bookings[self.bookings['booking_status'] == 'Active']
            booked_dates = [datetime.strptime(date, '%Y-%m-%d').date() for date in active_bookings['dosing_date']]
        
        available_dates = [date for date in dates if date not in booked_dates]
        return available_dates
    
    def get_pre_scan_date(self, dosing_date):
        """Get pre-scan date (day before dosing)"""
        return dosing_date - timedelta(days=1)
    
    def get_follow_up_date(self, dosing_date, group):
        """Get follow-up date (2 weeks after dosing)"""
        follow_up = dosing_date + timedelta(days=14)
        
        # Adjust to the correct day of week if needed
        # For Wednesday group, the follow-up should be on Thursday
        if group == 'WEDNESDAY':
            target_day = 3  # Thursday
            while follow_up.weekday() != target_day:
                follow_up += timedelta(days=1)
        # For Saturday group, the follow-up should be on Sunday
        else:
            target_day = 6  # Sunday
            while follow_up.weekday() != target_day:
                follow_up += timedelta(days=1)
                
        return follow_up
    
    def get_baseline_date(self, dosing_date):
        """Get the closest Monday that is at least 22 days before dosing"""
        earliest_allowed = dosing_date - timedelta(days=60)  # Don't go too far back
        latest_allowed = dosing_date - timedelta(days=22)    # At least 22 days before
        
        # Find the closest Monday to latest_allowed that's still valid
        current = latest_allowed
        while current.weekday() != 0:  # Monday is 0
            current -= timedelta(days=1)
        
        # If we went back too far, there's no valid date
        if current < earliest_allowed:
            return None
            
        return current
    
    def get_available_pre_dosing_times(self, pre_dosing_date, group):
        """Check available time slots for pre-dosing visit"""
        if 'pre_dosing_date' not in self.bookings.columns or self.bookings.empty:
            return ["Daytime", "Evening"]
        
        # Get active bookings for this date
        active_bookings = self.bookings[
            (self.bookings['booking_status'] == 'Active') & 
            (self.bookings['pre_dosing_date'] == pre_dosing_date.strftime('%Y-%m-%d'))
        ]
        
        # Get already booked times for this date
        booked_times = active_bookings['pre_dosing_time'].tolist()
        
        # Return available times
        all_times = ["Daytime", "Evening"]
        available_times = [time for time in all_times if time not in booked_times]
        
        return available_times
    
    def get_available_follow_up_times(self, follow_up_date, group):
        """Check available time slots for follow-up visit"""
        if 'follow_up_date' not in self.bookings.columns or self.bookings.empty:
            return ["Daytime", "Evening"]
        
        # Get active bookings for this date
        active_bookings = self.bookings[
            (self.bookings['booking_status'] == 'Active') & 
            (self.bookings['follow_up_date'] == follow_up_date.strftime('%Y-%m-%d'))
        ]
        
        # Get already booked times for this date
        booked_times = active_bookings['follow_up_time'].tolist()
        
        # Return available times
        all_times = ["Daytime", "Evening"]
        available_times = [time for time in all_times if time not in booked_times]
        
        return available_times
    
    def check_baseline_availability(self, baseline_date, group):
        """Check if the baseline slot is available"""
        if 'baseline_date' not in self.bookings.columns or self.bookings.empty:
            return True
        
        # Target time based on group
        target_time = "Daytime" if group == "WEDNESDAY" else "Evening"
        
        # Get active bookings for this date and time
        active_bookings = self.bookings[
            (self.bookings['booking_status'] == 'Active') & 
            (self.bookings['baseline_date'] == baseline_date.strftime('%Y-%m-%d')) &
            (self.bookings['baseline_time'] == target_time)
        ]
        
        # If there are no bookings for this slot, it's available
        return len(active_bookings) == 0
    
    def book_participant(self, name, participant_id, email, group, baseline_date, pre_dosing_date, 
                         dosing_date, follow_up_date, pre_dosing_time, follow_up_time):
        """Create a booking for a participant"""
        # Validate dates
        if not self._validate_booking(baseline_date, pre_dosing_date, dosing_date, follow_up_date, group):
            return False, "Invalid booking dates"
        
        # Check if participant already exists with active booking
        if participant_id in self.bookings[self.bookings['booking_status'] == 'Active']['participant_id'].values:
            return False, "Participant ID already has an active booking"
        
        # Set times based on group
        baseline_time = "Daytime" if group == "WEDNESDAY" else "Evening"
        
        # Add to bookings dataframe
        new_booking = pd.DataFrame({
            'name': [name],
            'participant_id': [participant_id],
            'email': [email],
            'group': [group],
            'baseline_date': [baseline_date.strftime('%Y-%m-%d')],
            'baseline_time': [baseline_time],
            'pre_dosing_date': [pre_dosing_date.strftime('%Y-%m-%d')],
            'pre_dosing_time': [pre_dosing_time],
            'dosing_date': [dosing_date.strftime('%Y-%m-%d')],
            'dosing_time': ['All Day'],
            'follow_up_date': [follow_up_date.strftime('%Y-%m-%d')],
            'follow_up_time': [follow_up_time],
            'booking_status': ['Active'],
            'notes': [''],
            'booking_time': [datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
        })
        
        self.bookings = pd.concat([self.bookings, new_booking], ignore_index=True)
        
        # Save to file
        self._save_bookings()
        
        # Send confirmation emails
        self._send_confirmation_email(name, participant_id, email, group, 
                                     baseline_date, baseline_time, 
                                     pre_dosing_date, pre_dosing_time, 
                                     dosing_date, 
                                     follow_up_date, follow_up_time)
        
        return True, "Booking successful"
    
    def cancel_booking(self, participant_id, reason):
        """Cancel a booking for a participant"""
        if participant_id not in self.bookings['participant_id'].values:
            return False, "Participant ID not found"
        
        # Find the participant's index
        idx = self.bookings[self.bookings['participant_id'] == participant_id].index
        
        # Update booking status and add cancellation note
        self.bookings.loc[idx, 'booking_status'] = 'Cancelled'
        self.bookings.loc[idx, 'notes'] = f"Cancelled: {reason}"
        self.bookings.loc[idx, 'cancellation_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Save to file
        self._save_bookings()
        
        # Send cancellation email (optional)
        # self._send_cancellation_email(participant_id)
        
        return True, "Booking cancelled successfully"
    
    def reset_all_bookings(self):
        """Reset all bookings (for piloting)"""
        if os.path.exists(self.bookings_file):
            # Create a backup first
            backup_file = f"study_bookings_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(backup_file, 'w') as f:
                f.write(self.bookings.to_json(orient='records'))
        
        # Clear the bookings
        self.bookings = pd.DataFrame(columns=[
            'name', 'participant_id', 'email', 'group', 'baseline_date', 
            'pre_dosing_date', 'dosing_date', 'follow_up_date',
            'booking_status', 'notes'
        ])
        
        # Save to file
        self._save_bookings()
        
        return True, f"All bookings reset. Backup created: {backup_file}"
    
    def generate_calendar_file(self, name, participant_id, group, 
                           baseline_date, baseline_time, 
                           pre_dosing_date, pre_dosing_time, 
                           dosing_date, 
                           follow_up_date, follow_up_time):
        """Generate an iCalendar file with all appointments"""
        cal = Calendar()
        
        # Helper function to create datetime objects with appropriate times
        def get_start_end_times(date, time_slot):
            date_str = date.strftime('%Y-%m-%d')
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            
            if time_slot == "Daytime":
                start_time = date_obj.replace(hour=9, minute=0)
                end_time = date_obj.replace(hour=12, minute=0)
            elif time_slot == "Evening":
                start_time = date_obj.replace(hour=14, minute=0)
                end_time = date_obj.replace(hour=17, minute=0)
            elif time_slot == "All Day":
                start_time = date_obj.replace(hour=9, minute=0)
                end_time = date_obj.replace(hour=17, minute=0)
            
            return start_time, end_time
        
        # Visit 1: Baseline
        baseline_start, baseline_end = get_start_end_times(baseline_date, baseline_time)
        baseline_event = Event()
        baseline_event.name = "Study Visit 1: Baseline"
        baseline_event.begin = baseline_start
        baseline_event.end = baseline_end
        baseline_event.description = f"Baseline visit for study participant {participant_id}. Includes surveys and computer tasks (about 3 hours)."
        baseline_event.location = "Research Center"
        cal.events.add(baseline_event)
        
        # Visit 2: Pre-dosing
        pre_dosing_start, pre_dosing_end = get_start_end_times(pre_dosing_date, pre_dosing_time)
        pre_dosing_event = Event()
        pre_dosing_event.name = "Study Visit 2: Pre-dosing Scans"
        pre_dosing_event.begin = pre_dosing_start
        pre_dosing_event.end = pre_dosing_end
        pre_dosing_event.description = f"Pre-dosing visit for study participant {participant_id}. Includes surveys, computer tasks, and fMRI movie scan (about 5 hours)."
        pre_dosing_event.location = "Research Center"
        cal.events.add(pre_dosing_event)
        
        # Visit 3: Dosing
        dosing_start, dosing_end = get_start_end_times(dosing_date, "All Day")
        dosing_event = Event()
        dosing_event.name = "Study Visit 3: Dosing Day"
        dosing_event.begin = dosing_start
        dosing_event.end = dosing_end
        dosing_event.description = f"Dosing day for study participant {participant_id}. Full day visit."
        dosing_event.location = "Research Center"
        cal.events.add(dosing_event)
        
        # Visit 4: Follow-up
        follow_up_start, follow_up_end = get_start_end_times(follow_up_date, follow_up_time)
        follow_up_event = Event()
        follow_up_event.name = "Study Visit 4: Follow-up Scans"
        follow_up_event.begin = follow_up_start
        follow_up_event.end = follow_up_end
        follow_up_event.description = f"Follow-up visit for study participant {participant_id}. Includes surveys, computer tasks, and fMRI movie scan (about 5 hours)."
        follow_up_event.location = "Research Center"
        cal.events.add(follow_up_event)
        
        # Return calendar as string
        return cal.serialize()
    
    def _validate_booking(self, baseline, pre_dosing, dosing, follow_up, group):
        """Validate the booking dates"""
        # Ensure dosing is on correct day of week
        if group == 'WEDNESDAY' and dosing.weekday() != 2:  # Wednesday is 2
            return False
            
        if group == 'SATURDAY' and dosing.weekday() != 5:  # Saturday is 5
            return False
        
        # Ensure pre-dosing is day before dosing
        if (dosing - pre_dosing).days != 1:
            return False
        
        # Ensure baseline is at least 22 days before dosing
        if (dosing - baseline).days < 22:
            return False
        
        # Ensure baseline is on Monday
        if baseline.weekday() != 0:  # Monday is 0
            return False
        
        # For Wednesday group, follow-up should be Thursday
        if group == 'WEDNESDAY' and follow_up.weekday() != 3:
            return False
            
        # For Saturday group, follow-up should be Sunday
        if group == 'SATURDAY' and follow_up.weekday() != 6:
            return False
        
        return True
    
    def _send_confirmation_email(self, name, participant_id, email, group, 
                                baseline_date, baseline_time, 
                                pre_dosing_date, pre_dosing_time, 
                                dosing_date, 
                                follow_up_date, follow_up_time):
        """Send confirmation email to participant and research team"""
        try:
            # Format dates for email
            baseline_formatted = baseline_date.strftime('%A, %B %d, %Y')
            pre_dosing_formatted = pre_dosing_date.strftime('%A, %B %d, %Y')
            dosing_formatted = dosing_date.strftime('%A, %B %d, %Y')
            follow_up_formatted = follow_up_date.strftime('%A, %B %d, %Y')
            
            # Create email content
            email_subject = f"Study Visit Booking Confirmation - Participant {participant_id}"
            
            email_body = f"""
            <html>
            <body>
            <h2>Study Visit Booking Confirmation</h2>
            
            <p>Dear {name},</p>
            
            <p>Thank you for booking your study visits. Your appointments have been scheduled as follows:</p>
            
            <table border="1" cellpadding="5" cellspacing="0">
                <tr>
                    <th>Visit</th>
                    <th>Date</th>
                    <th>Time</th>
                </tr>
                <tr>
                    <td>Visit 1 (Baseline)</td>
                    <td>{baseline_formatted}</td>
                    <td>{baseline_time}</td>
                </tr>
                <tr>
                    <td>Visit 2 (Pre-dosing)</td>
                    <td>{pre_dosing_formatted}</td>
                    <td>{pre_dosing_time}</td>
                </tr>
                <tr>
                    <td>Visit 3 (Dosing)</td>
                    <td>{dosing_formatted}</td>
                    <td>All Day</td>
                </tr>
                <tr>
                    <td>Visit 4 (Follow-up)</td>
                    <td>{follow_up_formatted}</td>
                    <td>{follow_up_time}</td>
                </tr>
            </table>
            
            <p>Important Information:</p>
            <ul>
                <li>Please arrive 15 minutes before your scheduled appointment time</li>
                <li>Bring a valid ID and your appointment confirmation</li>
                <li>If you need to reschedule, please contact us at least 48 hours in advance</li>
                <li>For any questions, email us at dipp-project@ucl.ac.uk</li>
            </ul>
            
            <p>Your Participant ID: <strong>{participant_id}</strong></p>
            <p>You are in the <strong>{group}</strong> group.</p>
            
            <p>Thank you for your participation!</p>
            <p>The Research Team</p>
            </body>
            </html>
            """
            
            # In a production app, you would use your email server credentials here
            # For demo purposes, we'll just show what would be emailed
            st.session_state['email_sent'] = {
                'to_participant': email,
                'to_team': 'dipp-project@ucl.ac.uk',
                'subject': email_subject,
                'body': email_body
            }
            
            # Note: In the real deployment, use this code to actually send emails
            # Connect to email server and send emails
            """
            # Create message for participant
            msg_participant = MIMEMultipart()
            msg_participant['From'] = 'your-email@ucl.ac.uk'
            msg_participant['To'] = email
            msg_participant['Subject'] = email_subject
            msg_participant.attach(MIMEText(email_body, 'html'))
            
            # Create message for research team
            msg_team = MIMEMultipart()
            msg_team['From'] = 'your-email@ucl.ac.uk'
            msg_team['To'] = 'dipp-project@ucl.ac.uk'
            msg_team['Subject'] = f"[ADMIN] {email_subject}"
            msg_team.attach(MIMEText(email_body + f"\n\nParticipant Email: {email}", 'html'))
            
            # Connect to SMTP server
            server = smtplib.SMTP('smtp.ucl.ac.uk', 587)
            server.starttls()
            server.login('your-email@ucl.ac.uk', 'your-password')
            
            # Send emails
            server.send_message(msg_participant)
            server.send_message(msg_team)
            
            server.quit()
            """
            
            return True
        except Exception as e:
            print(f"Error sending email: {e}")
            return False
        
    def get_all_bookings(self):
        """Return all bookings"""
        return self.bookings
    
    def _save_bookings(self):
        """Save bookings to file"""
        with open(self.bookings_file, 'w') as f:
            f.write(self.bookings.to_json(orient='records'))

# Initialize the booking system
@st.cache_resource
def get_booking_system():
    return StudyBookingSystem()

booking_system = get_booking_system()

# Initialize session state for confirmation
if 'email_sent' not in st.session_state:
    st.session_state['email_sent'] = None

# App title
st.title("Study Visit Booking System")

# Study information
st.markdown("""
## About the Study Visits

This study requires participants to attend four separate visits:

1. **Dosing Day (Visit 3)**: This is the main visit where you'll spend all day at the center. You can choose either a Wednesday or Saturday.

2. **Pre-dosing Visit (Visit 2)**: The day before your dosing, you'll need to come in for about 5 hours to complete surveys, computer tasks, and have an fMRI movie scan. You can choose either daytime or evening.

3. **Baseline Visit (Visit 1)**: About 3 weeks before your dosing day, you'll come in for your first baseline visit to do surveys and computer tasks (about 3 hours).

4. **Follow-up Visit (Visit 4)**: About 2 weeks after your dosing day, you'll come in for about 5 hours to complete surveys, computer tasks, and have an fMRI movie scan. You can choose either daytime or evening.

## Our Scheduling System

We have two scheduling groups:

### Wednesday Dosing Group:
- **Dosing Day**: Wednesday (all day)
- **Pre-dosing Visit**: Tuesday (day before), choose daytime or evening
- **Baseline Visit**: Monday (at least 22 days before dosing), daytime only
- **Follow-up Visit**: Thursday (about 2 weeks after dosing), choose daytime or evening

### Saturday Dosing Group:
- **Dosing Day**: Saturday (all day)
- **Pre-dosing Visit**: Friday (day before), choose daytime or evening
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
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Date**: {baseline_date.strftime('%A, %B %d, %Y')}")
                with col2:
                    baseline_time = "Daytime" if group == "WEDNESDAY" else "Evening"
                    st.markdown(f"**Time**: {baseline_time}")
                
                if not baseline_available:
                    st.warning(f"⚠️ This baseline slot is already booked. Please select a different dosing date.")
                
                # Visit 2: Pre-dosing
                st.markdown("#### Visit 2: Pre-dosing")
                col1, col2 = st.columns(2)
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
                            options=available_pre_dosing_times
                        )
                
                # Visit 3: Dosing Day
                st.markdown("#### Visit 3: Dosing Day")
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Date**: {dosing_date.strftime('%A, %B %d, %Y')}")
                with col2:
                    st.markdown("**Time**: All Day")
                
                # Visit 4: Follow-up
                st.markdown("#### Visit 4: Follow-up")
                col1, col2 = st.columns(2)
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
                            options=available_follow_up_times
                        )
                
                # Step 5: Submit booking
                st.subheader("Step 5: Confirm Booking")
                
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
                        col1, col2, col3 = st.columns(3)
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
                        
                        # Generate calendar file
                        calendar_data = booking_system.generate_calendar_file(
                            name, participant_id, group, 
                            baseline_date, baseline_time, 
                            pre_dosing_date, pre_dosing_time, 
                            dosing_date, 
                            follow_up_date, follow_up_time
                        )
                        
                        # Add email confirmation message
                        st.markdown("---")
                        st.success("A confirmation email has been sent to your email address and the research team.")
                        
                        # Offer calendar download
                        st.download_button(
                            label="Download Calendar File (.ics)",
                            data=calendar_data,
                            file_name=f"study_visits_{participant_id}.ics",
                            mime="text/calendar"
                        )
                        
                        st.markdown("Please take a screenshot or print this page for your records.")
                        
                        # Show email preview
                        with st.expander("Email Preview"):
                            if st.session_state['email_sent']:
                                st.markdown(st.session_state['email_sent']['body'], unsafe_allow_html=True)
                    else:
                        st.error(f"❌ Booking Failed: {message}")
    else:
        st.info("Please enter your name, participant ID, and email address to continue.")

with tab2:
    st.header("Admin Panel")
    
    # Password protection for admin
    admin_password = st.text_input("Admin Password (enter 'admin' for demo)", type="password")
    
    if admin_password == "admin":
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
                st.rerun()
            
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
            
            # Date range management
            st.markdown("#### Manage Date Range")
            st.info("In the production version, you can add controls here to adjust the available date range.")
            
            # Email settings
            st.markdown("#### Email Settings")
            st.info("In the production version, you can add controls here to configure email settings.")
    
    elif admin_password:
        st.error("Incorrect password")
import streamlit as st
from supabase import create_client, Client
import random
import time
import io
import uuid
from PIL import Image, ImageDraw, ImageFont
import pandas as pd
from datetime import datetime
import os

# --- Initial Setup ---
st.set_page_config(
    page_title="Number Assignment System",
    layout="centered",
    initial_sidebar_state="expanded"
)

# --- CSS Styling ---
st.markdown("""
<style>
    .main-header {text-align: center; margin-bottom: 30px;}
    .number-display {font-size: 72px; text-align: center; margin: 30px 0;}
    .success-msg {background-color: #d4edda; color: #155724; padding: 10px; border-radius: 5px;}
    .error-msg {background-color: #f8d7da; color: #721c24; padding: 10px; border-radius: 5px;}
</style>
""", unsafe_allow_html=True)

# --- Functions ---

def get_supabase_client() -> Client:
    """Establishes a connection to Supabase using environment variables."""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        st.error("Supabase credentials not configured in the environment.")
        return None
    try:
        client = create_client(supabase_url, supabase_key)
        return client
    except Exception as e:
        st.error(f"Error connecting to Supabase: {str(e)}")
        return None

def check_table_exists(supabase, table_name):
    """Checks if a specific table exists in Supabase."""
    try:
        supabase.table(table_name).select("*").limit(1).execute()
        return True
    except Exception:
        return False

def create_meeting_table(supabase, table_name, meeting_name, max_number=999):
    """Creates a new table for a meeting in Supabase and registers metadata."""
    try:
        supabase.table("meetings_metadata").insert({
            "table_name": table_name,
            "meeting_name": meeting_name,
            "created_at": datetime.now().isoformat(),
            "max_number": max_number
        }).execute()

        for i in range(1, max_number + 1):
            supabase.table(table_name).insert({"number": i, "assigned": False, "user_id": None}).execute()

        return True
    except Exception as e:
        st.error(f"Error creating meeting table: {str(e)}")
        return False

def get_available_meetings(supabase):
    """Retrieves the list of available meetings from the metadata table."""
    try:
        response = supabase.table("meetings_metadata").select("*").execute()
        return response.data if response.data else []
    except Exception as e:
        st.error(f"Error retrieving meetings: {str(e)}")
        return []

def generate_number_image(number):
    """Generates an image with only the assigned number."""
    width, height = 600, 300
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("Arial.ttf", 200)
    except IOError:
        font = ImageFont.load_default()

    text = str(number)
    text_width, text_height = draw.textsize(text, font=font)
    text_position = ((width - text_width) // 2, (height - text_height) // 2)
    draw.text(text_position, text, font=font, fill=(0, 0, 0))

    img_buffer = io.BytesIO()
    img.save(img_buffer, format="PNG")
    img_buffer.seek(0)
    return img_buffer

def generate_participant_link(table_name):
    """Generates a link for participants to access the meeting."""
    base_url = "https://app-number.streamlit.app"
    return f"{base_url}/?table={table_name}&mode=participant"

# --- Session Management ---
if "user_id" not in st.session_state:
    st.session_state["user_id"] = str(uuid.uuid4())

# --- Page Logic ---
query_params = st.query_params
mode = query_params.get("mode", "master")
table_name_from_url = query_params.get("table", None)

if mode == "participant" and table_name_from_url:
    # --- Participant Mode ---
    st.markdown("<h1 class='main-header'>Get Your Number</h1>", unsafe_allow_html=True)
    supabase = get_supabase_client()
    if not supabase:
        st.stop()
    
    user_id = st.session_state["user_id"]
    assigned_number = None

    try:
        existing = supabase.table(table_name_from_url).select("number").eq("user_id", user_id).execute()
        if existing.data:
            assigned_number = existing.data[0]["number"]
        else:
            available_numbers = supabase.table(table_name_from_url).select("number").eq("assigned", False).execute().data
            if available_numbers:
                assigned_number = random.choice([num["number"] for num in available_numbers])
                supabase.table(table_name_from_url).update({"assigned": True, "user_id": user_id}).eq("number", assigned_number).execute()
    except Exception as e:
        st.error(f"Error assigning number: {str(e)}")
    
    if assigned_number:
        st.markdown(f"<div class='success-msg'><p>Your assigned number is:</p><div class='number-display'>{assigned_number}</div></div>", unsafe_allow_html=True)
        if st.button("Save as Image"):
            img_buffer = generate_number_image(assigned_number)
            st.download_button("Download Image", img_buffer, file_name=f"number_{assigned_number}.png", mime="image/png")

else:
    # --- Master Mode ---
    st.sidebar.title("Admin Panel")
    page = st.sidebar.radio("Select", ["Manage Meetings", "Share Meeting Link"])

    supabase = get_supabase_client()
    if not supabase:
        st.stop()

    if page == "Manage Meetings":
        st.markdown("<h1 class='main-header'>Manage Meetings</h1>", unsafe_allow_html=True)

        with st.form("create_meeting_form"):
            meeting_name = st.text_input("Meeting Name")
            max_number = st.number_input("Maximum Number", min_value=10, max_value=10000, value=999)
            submit_button = st.form_submit_button("Create Meeting")
            
            if submit_button and meeting_name:
                table_name = f"meeting_{int(time.time())}"
                if create_meeting_table(supabase, table_name, meeting_name, max_number):
                    st.success(f"Meeting '{meeting_name}' created successfully!")

        st.subheader("Existing Meetings")
        meetings = get_available_meetings(supabase)
        if meetings:
            df = pd.DataFrame(meetings)
            st.dataframe(df)
        else:
            st.info("No meetings found.")

    elif page == "Share Meeting Link":
        st.markdown("<h1 class='main-header'>Share Meeting Link</h1>", unsafe_allow_html=True)
        meetings = get_available_meetings(supabase)
        if meetings:
            selected = st.selectbox("Select a meeting", [m["meeting_name"] for m in meetings])
            table_name = next(m["table_name"] for m in meetings if m["meeting_name"] == selected)
            st.markdown(f"**Participant Link:** [{generate_participant_link(table_name)}]({generate_participant_link(table_name)})")

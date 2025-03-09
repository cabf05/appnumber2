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
    """Establishes a connection to Supabase."""
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

def generate_number_image(number):
    """Generates an image with only the assigned number."""
    width, height = 600, 300
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("Arial.ttf", 200)
    except IOError:
        font = ImageFont.load_default()
    
    number_text = str(number)
    bbox = draw.textbbox((0, 0), number_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    text_position = ((width - text_width) // 2, (height - text_height) // 2)
    draw.text(text_position, number_text, font=font, fill=(0, 0, 100))
    
    img_buffer = io.BytesIO()
    img.save(img_buffer, format="PNG")
    img_buffer.seek(0)
    return img_buffer

# --- Initialize Session Variables ---
if "user_id" not in st.session_state:
    st.session_state["user_id"] = str(uuid.uuid4())

if "assigned_number" not in st.session_state:
    st.session_state["assigned_number"] = None

# --- Participant Mode ---
query_params = st.query_params
mode = query_params.get("mode", "master")
table_name = query_params.get("table", None)

if mode == "participant" and table_name:
    st.markdown("<h1 class='main-header'>Get Your Number</h1>", unsafe_allow_html=True)
    supabase = get_supabase_client()
    if not supabase:
        st.stop()

    if not check_table_exists(supabase, table_name):
        st.error("Meeting not found or invalid.")
        st.stop()

    user_id = st.session_state["user_id"]

    # Check if the user already has an assigned number
    try:
        existing = supabase.table(table_name).select("number").eq("user_id", user_id).execute()
        if existing.data:
            assigned_number = existing.data[0]["number"]
            st.session_state["assigned_number"] = assigned_number
        else:
            with st.spinner("Assigning a number..."):
                response = supabase.table(table_name).select("number").eq("assigned", False).execute()
                if response.data:
                    available_numbers = [row["number"] for row in response.data]
                    assigned_number = random.choice(available_numbers)
                    supabase.table(table_name).update({
                        "assigned": True,
                        "assigned_at": datetime.now().isoformat(),
                        "user_id": user_id
                    }).eq("number", assigned_number).execute()
                    st.session_state["assigned_number"] = assigned_number
                else:
                    st.error("All numbers have been assigned!")
                    st.stop()
    except Exception as e:
        st.error(f"Error assigning number: {str(e)}")
        st.stop()
    
    st.markdown(f"""
    <div class='success-msg'>
        <p>Your assigned number is:</p>
        <div class='number-display'>{st.session_state['assigned_number']}</div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("Save as Image"):
        with st.spinner("Generating image..."):
            img_buffer = generate_number_image(st.session_state["assigned_number"])
            st.image(img_buffer)
            st.download_button(
                "Download Image",
                img_buffer,
                file_name=f"my_number_{st.session_state['assigned_number']}.png",
                mime="image/png"
            )

else:
    st.markdown("<h1 class='main-header'>Meeting Management</h1>", unsafe_allow_html=True)
    st.info("Please enter the meeting as a participant to receive a number.")

import streamlit as st
import os
import sys

# Ensure project root is strictly first in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not sys.path or sys.path[0] != PROJECT_ROOT:
    if PROJECT_ROOT in sys.path:
        sys.path.remove(PROJECT_ROOT)
    sys.path.insert(0, PROJECT_ROOT)

from utils.styles import inject_custom_css, render_header, LOGO_PATH


st.set_page_config(
    page_title="Get Help Now | CareAtZero",
    page_icon=LOGO_PATH,
    layout="wide"
)

inject_custom_css()
render_header("help")

st.markdown('<div class="cz-title">Get help now</div>', unsafe_allow_html=True)

# Big tap-to-call buttons. On a phone, tel: links open the dialer directly.
st.markdown("""
<div class="cz-help" style="background:#FDECEC; color:#7A1414;">
  <h4 style="color:#7A1414 !important;">Life-threatening emergency?</h4>
  <p>Chest pain, trouble breathing, severe bleeding or injury.</p>
  <a href="tel:911" style="background:#B42318;">Call 911</a>
</div>
<div class="cz-help" style="background:#E6F0FD; color:#0A3D91;">
  <h4 style="color:#0A3D91 !important;">Mental health or suicide crisis</h4>
  <p>Free and available 24/7. Call or text to talk with someone.</p>
  <a href="tel:988" style="background:#0E2A5C;">Call or text 988</a>
</div>
""", unsafe_allow_html=True)

if st.button("Not an emergency? Find a free clinic", icon=":material/search:", width="stretch"):
    st.switch_page("pages/1_🔍_Find_Free_Care.py")

st.caption("CareAtZero does not diagnose symptoms or give medical advice. "
           "If this is a medical emergency, call 911 or go to the nearest emergency room.")

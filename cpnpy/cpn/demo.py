import streamlit as st

st.title("Hello Streamlit")

x = st.slider("Pick a number", 0, 100, 25)
st.write("Squared:", x * x)
import streamlit as st
from UsersDAO import UsersDAO


def user_is(user:UsersDAO(), api_key:str, api_secret:str):
    usr = user(api_key=api_key,api_secret= api_secret)
    return usr

# Create an empty container
placeholder = st.empty()

# Insert a form in the container
with placeholder.form("Api_user"):
    st.markdown("#### Insert your api credentials")
    nick_user = st.text_input("API KEY", type="password")
    password = st.text_input("API SECRET", type="password")


    check_button_placer, sign_button_placer, = st.columns([6, 1])
    with check_button_placer:
        check_button = st.form_submit_button("Check Nickname")
    with sign_button_placer:
        confirm_button = st.form_submit_button("Confirm")




import streamlit as st
from UsersDAO import UsersDAO
from DbService import DbService
from Yaml_authenticator import Yaml_authenticator
from User import User


def Sign_form():

    dbs = DbService()
    st.title("Welcome dear Binancer")
    st.write("Please insert your Binance Api Key and a valid nickname")
    New_user_Registration = st.form(key="New_user_Registration", clear_on_submit=True)

    with (New_user_Registration):
        with st.container():
            c11, c12 = st.columns(2)
            with c11:
                nick = st.text_input(label="Nickname", max_chars=10)
            with c12:
                password = st.text_input(label="Password", max_chars=10, type="password")

        with st.container():
            c21, c22 = st.columns(2)
            with c21:
                ApiKey = st.text_input(label="Api Key")
            with c22:
                ApiSec = st.text_input(label="Secret Key", type="password")

        with st.container():
            c31, c32 = st.columns(2)
            with c31:
                email = st.text_input(label="Email")
            with c32:
                full_name = st.text_input(label="Full Name")

        submit_button = st.form_submit_button(label='Submit')

        usr_yml = None
        auth_status = None
        if submit_button:
            Usr = UsersDAO(api_key=ApiKey, api_secret=ApiSec, nick_name=nick, pass_word=password, DbServ=dbs)
            if not Usr.is_user_registered():
                Usr.insert_user()
                # RIEMPIRE TABELLE CLIENTE
                # REGISTRARE DATA REGISTRAZIONE
                usr_yml = User(nicknam=nick, password=password, name=full_name, email=email)
                yml_op = Yaml_authenticator(Usr=usr_yml)
                yml_op.SignIn_yaml()
                st.success(f"Hello dear {nick}, you have successufully registered")
                auth_status = True
            elif Usr.is_user_registered():
                st.warning(f"Please, choose a different nickname")
                auth_status = False
            else:
                st.warning("something goes wrong")
                auth_status = False

    return usr_yml, auth_status


def Login_form():
    Usr = User()
    Yml_auth = Yaml_authenticator(Usr=Usr)  # Utente vuoto
    # Login form
    name, authentication_status, username, password = Yml_auth.Yaml_login_form()
    return name, authentication_status, username, password

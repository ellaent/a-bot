from decouple import config

TOKEN = config("TOKEN")

DB_NAME = config("DB_NAME")
DB_HOST = config("DB_HOST")
DB_USERNAME = config("DB_USERNAME")
DB_PASSWORD = config("DB_PASSWORD")

OWM_TOKEN = config("OWM_TOKEN")

HCTI_API_ENDPOINT = config("HCTI_API_ENDPOINT")
HCTI_API_USER_ID = config("HCTI_API_USER_ID")
HCTI_API_KEY = config("HCTI_API_KEY")

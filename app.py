# app.py
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time

st.set_page_config(page_title="Mayomide Store Price Manager", layout="wide")

# -----------------------
# CONFIG: set your sheet name here
SHEET_NAME = "Mayomide Store Database"
# -----------------------

# --- Google Sheets auth ---
@st.cache_resource
def get_gsheet_client(creds_json_path="service_account.json"):
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_json_path, scope)
    client = gspread.authorize(creds)
    return client

def load_sheets(client):
    sh = client.open(SHEET_NAME)
    products_df = pd.DataFrame(sh.worksheet("products").get_all_records())
    categories_df = pd.DataFrame(sh.worksheet("categories").get_all_records())
    history_df = pd.DataFrame(sh.worksheet("price_history").get_all_records())
    settings_df = pd.DataFrame(sh.worksheet("app_settings").get_all_records())
    return sh, products_df, categories_df, history_df, settings_df

def get_setting(settings_df, key, default=None):
    row = settings_df[settings_df['Field'] == key]
    if not row.empty:
        return str(row.iloc[0]['Value'])
    return default

# --- Utility to find product row in sheet by id ---
def find_product_row_index(products_df, product_id):
    # gspread rows are 1-indexed; header row is row 1, so data starts at 2
    idxs = products_df.index[products_df['id'] == product_id].tolist()
    if not idxs:
        return None
    return idxs[0] + 2  # +2 because index 0 -> row 2

# --- Append to history and update product ---
def record_price_change(sh, product_row_idx, product_id, old_price, new_price, updated_by, note):
    # Update products sheet (current_price, last_updated, updated_by)
    products_ws = sh.worksheet("products")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # find col numbers by header for safety
    headers = products_ws.row_values(1)
    col_map = {h: i+1 for i,h in enumerate(headers)}
    # update cells
    if 'current_price' in col_map:
        products_ws.update_cell(product_row_idx, col_map['current_price'], new_price)
    if 'last_updated' in col_map:
        products_ws.update_cell(product_row_idx, col_map['last_updated'], timestamp)
    if 'updated_by' in col_map:
        products_ws.update_cell(product_row_idx, col_map['updated_by'], updated_by)

    # Append to history sheet
    history_ws = sh.worksheet("price_history")
    # attempt to find next id (if 'id' is numeric)
    try:
        history_vals = history_ws.get_all_values()
        next_id = len(history_vals)  # rough, since header present
    except Exception:
        next_id = ""
    row = [next_id, product_id, old_price, new_price, updated_by, timestamp, note]
    history_ws.append_row(row, value_input_option='USER_ENTERED')


# -----------------------
# Main
st.title("💜 Mayomide Store Price Manager")
st.caption("View and update product prices. Updates are logged in Price History.")

# Load client and sheets
try:
    client = get_gsheet_client()
    sh, products_df, categories_df, history_df, settings_df = load_sheets(client)
except Exception as e:
    st.error("Unable to load Google Sheet. Make sure `service_account.json` is present and the service account has access to the sheet.")
    st.exception(e)
    st.stop()

# Settings
update_password = get_setting(settings_df, "update_password", default="1234")

# Sidebar: basic info & refresh
with st.sidebar:
    st.header("App Info")
    st.write("Sheet:", SHEET_NAME)
    st.write("Products:", len(products_df))
    st.write("Categories:", len(categories_df))
    if st.button("Refresh data"):
        st.experimental_rerun()
    st.markdown("---")
    st.write("Password for updates is stored in `app_settings` sheet (you can change it there).")

# Filters: Search, Category, Product
col1, col2, col3 = st.columns([4,2,3])
with col1:
    search_q = st.text_input("🔎 Search product name or SKU", value="")
with col2:
    cat_options = ["All"] + categories_df['name'].astype(str).tolist() if not categories_df.empty else ["All"]
    selected_cat = st.selectbox("Category", cat_options)
with col3:
    # Filter products by category & search
    filtered = products_df.copy()
    if selected_cat != "All" and 'category_id' in products_df.columns:
        # map category id -> name from categories_df
        cat_map = dict(zip(categories_df['id'], categories_df['name']))
        # create a name column for filtering
        filtered['category_name'] = filtered['category_id'].map(cat_map)
        filtered = filtered[filtered['category_name'] == selected_cat]
    if search_q:
        filtered = filtered[filtered['name'].astype(str).str.contains(search_q, case=False, na=False) |
                            filtered['id'].astype(str).str.contains(search_q, case=False, na=False)]
    product_options = filtered[['id','name']].apply(lambda r: f"{r['id']} - {r['name']}", axis=1).tolist()
    product_sel = st.selectbox("Product", [""] + product_options)

if product_sel == "":
    st.info("Select a product to view details.")
    st.stop()

# parse selected product id
sel_id = product_sel.split(" - ")[0]
product_row = products_df[products_df['id'] == (int(sel_id) if sel_id.isdigit() else sel_id)]
if product_row.empty:
    st.error("Selected product not found in sheet.")
    st.stop()

product = product_row.iloc[0].to_dict()

# Product display
left, right = st.columns([2,3])
with left:
    # image area (display placeholder or image_url if present)
    img_url = str(product.get('image_url','') or "").strip()
    if img_url:
        try:
            st.image(img_url, use_column_width=True, caption=product.get('name'))
        except Exception:
            st.write("Image URL present but couldn't load. Check URL.")
            st.empty()
    else:
        st.write("No image yet (add image_url in `products` sheet).")
        st.empty()

with right:
    st.subheader(product.get('name', 'Unnamed product'))
    unit = product.get('unit', '')
    st.write(f"**Unit:** {unit}")
    st.write(f"**Unit price (price for 1):** ₦{product.get('current_price')}")
    st.write(f"**Created price:** {product.get('current_price')}")
    st.write(f"**Last Updated:** {product.get('last_updated')}")
    st.write(f"**Updated By:** {product.get('updated_by')}")

    st.markdown("---")
    col_upd, col_hist = st.columns(2)
    if col_upd.button("🔧 Update Price"):
        # open password modal
        with st.modal("Enter update password"):
            pw = st.text_input("Enter update password", type="password")
            confirm = st.button("Confirm")
            if confirm:
                if str(pw) == str(update_password):
                    st.success("Password accepted. Enter new price below.")
                    # show update form
                    new_price = st.number_input("New Price (₦)", min_value=0.0, value=float(product.get('current_price') or 0))
                    who_options = ["Mom", "You", "Sibling1", "Sibling2", "Sibling3"]
                    who = st.selectbox("Who is updating?", who_options)
                    note = st.text_area("Note (optional)", height=80)
                    if st.button("Save price change"):
                        old_price = product.get('current_price')
                        # find product row index in sheet
                        prod_row_idx = find_product_row_index(products_df, product.get('id'))
                        try:
                            record_price_change(sh, prod_row_idx, product.get('id'), old_price, new_price, who, note)
                            st.success(f"Price updated from ₦{old_price} to ₦{new_price}")
                            time.sleep(1)
                            st.experimental_rerun()
                        except Exception as e:
                            st.error("Error saving price change. Check logs or sheet permissions.")
                            st.exception(e)
                else:
                    st.error("Access denied: wrong password.")

    if col_hist.button("📜 View Price History"):
        with st.expander("Price History (latest first)", expanded=True):
            ph = history_df[history_df['product_id'] == product.get('id')].copy()
            if ph.empty:
                st.info("No history available for this product yet.")
            else:
                # compute diff and pct
                ph['old_price'] = pd.to_numeric(ph['old_price'], errors='coerce')
                ph['new_price'] = pd.to_numeric(ph['new_price'], errors='coerce')
                ph['diff'] = ph['new_price'] - ph['old_price']
                ph['pct_change'] = ((ph['diff'] / ph['old_price']) * 100).round(2)
                ph = ph.sort_values(by='timestamp', ascending=False)
                st.dataframe(ph[['timestamp','old_price','new_price','diff','pct_change','updated_by','note']].rename(columns={
                    'timestamp':'Date',
                    'old_price':'Old ₦',
                    'new_price':'New ₦',
                    'diff':'Δ ₦',
                    'pct_change':'% Δ',
                    'updated_by':'By',
                    'note':'Note'
                }))

st.write("")  # whitespace
st.caption("Tip: change the update password anytime by editing the app_settings sheet (Field=update_password).")

# app.py
import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime
from typing import Optional

st.set_page_config(page_title="Mayomide Store Price Manager", layout="wide")

# -----------------------
# CONFIG: Supabase keys are read from st.secrets
# Set these in Streamlit Cloud or locally via ~/.streamlit/secrets.toml
# Required keys:
# SUPABASE_URL
# SUPABASE_KEY    (anon/public key)
# -----------------------

@st.cache_resource(show_spinner=False)
def get_supabase_client() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = get_supabase_client()

# ---------- Helpers ----------

def fetch_tables():
    """Fetch products, categories, history, settings into DataFrames"""
    # products
    p = supabase.table("products").select("*").order("id", desc=False).execute()
    products_df = pd.DataFrame(p.data) if p.data else pd.DataFrame(columns=['id','name','category_id','unit','current_price','image_url','last_updated','updated_by'])
    # categories
    c = supabase.table("categories").select("*").order("id", desc=False).execute()
    categories_df = pd.DataFrame(c.data) if c.data else pd.DataFrame(columns=['id','name'])
    # price_history
    h = supabase.table("price_history").select("*").order("timestamp", desc=True).execute()
    history_df = pd.DataFrame(h.data) if h.data else pd.DataFrame(columns=['id','product_id','old_price','new_price','updated_by','timestamp','note'])
    # app_settings (we expect 1 row)
    s = supabase.table("app_settings").select("*").limit(1).execute()
    settings = s.data[0] if s.data else {"update_password": ""}
    return products_df, categories_df, history_df, settings

def get_update_password(settings: dict) -> str:
    return settings.get("update_password") or ""

def display_product_card(product_row: pd.Series, categories_df: pd.DataFrame):
    st.image(product_row.get("image_url",""), width=220) if product_row.get("image_url") else st.write("No image yet (add `image_url` in Supabase).")
    st.markdown(f"### {product_row.get('name','Unnamed product')}")
    st.markdown(f"**Unit:** {product_row.get('unit','')}")
    st.markdown(f"**Unit price (price for 1):** ₦{product_row.get('current_price')}")
    st.markdown(f"**Created price:** ₦{product_row.get('current_price')}")
    last_up = product_row.get('last_updated') or ""
    if last_up:
        # ensure readable format
        try:
            last_up_dt = pd.to_datetime(last_up)
            last_up = last_up_dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            last_up = str(last_up)
    st.markdown(f"**Last Updated:** {last_up}")
    st.markdown(f"**Updated By:** {product_row.get('updated_by','')}")

def update_price(product_id, old_price, new_price, updated_by, note):
    # 1) append to price_history
    supabase.table("price_history").insert({
        "product_id": product_id,
        "old_price": old_price,
        "new_price": new_price,
        "updated_by": updated_by,
        "note": note
    }).execute()

    # 2) update products table
    supabase.table("products").update({
        "current_price": new_price,
        "last_updated": datetime.utcnow().isoformat(),
        "updated_by": updated_by
    }).eq("id", product_id).execute()

def change_shared_password(new_password: str):
    # update existing row; if none exists, insert
    r = supabase.table("app_settings").select("*").limit(1).execute()
    if r.data:
        row_id = r.data[0]["id"]
        supabase.table("app_settings").update({"update_password": new_password}).eq("id", row_id).execute()
    else:
        supabase.table("app_settings").insert({"update_password": new_password}).execute()

# ---------- UI ----------

st.title("💜 Mayomide Store Price Manager")
st.caption("Search, view, and update prices. All updates are saved to Price History.")

# Load data
with st.spinner("Loading data from Supabase..."):
    products_df, categories_df, history_df, settings = fetch_tables()

update_password = get_update_password(settings)

# Sidebar info and refresh
with st.sidebar:
    st.header("App Info")
    st.write("Supabase project:", st.secrets.get("SUPABASE_URL","(not set)"))
    st.write("Products:", len(products_df))
    st.write("Categories:", len(categories_df))
    if st.button("Refresh data"):
        st.experimental_rerun()
    st.markdown("---")
    st.write("Note: To change the shared update password, use Admin → Change password (protected).")

# --- Filters: search, category, product select
col1, col2, col3 = st.columns([4,2,3])

with col1:
    search_q = st.text_input("🔎 Search product name or ID", value="")

with col2:
    cat_options = ["All"] + categories_df['name'].astype(str).tolist() if not categories_df.empty else ["All"]
    selected_cat = st.selectbox("Category", cat_options)

with col3:
    # Filter products by category & search
    filtered = products_df.copy()
    if selected_cat != "All" and not categories_df.empty:
        # map category id -> name for filtering
        cat_map = dict(zip(categories_df['id'], categories_df['name']))
        filtered['category_name'] = filtered['category_id'].map(cat_map)
        filtered = filtered[filtered['category_name'] == selected_cat]
    if search_q:
        filtered = filtered[filtered['name'].astype(str).str.contains(search_q, case=False, na=False) |
                            filtered['id'].astype(str).str.contains(search_q, case=False, na=False)]
    product_options = filtered.apply(lambda r: f"{r['id']} - {r['name']}", axis=1).tolist() if not filtered.empty else []
    product_sel = st.selectbox("Product", [""] + product_options)

if product_sel == "":
    st.info("Select a product to view details.")
    st.stop()

sel_id = int(product_sel.split(" - ")[0])
product_row = products_df[products_df['id'] == sel_id].iloc[0]

# Display product card
left, right = st.columns([2,3])
with left:
    if product_row.get("image_url"):
        st.image(product_row.get("image_url"), caption=product_row.get("name"), use_column_width=True)
    else:
        # placeholder area (keeps card layout consistent)
        st.write("No image yet (add `image_url` in Supabase).")

with right:
    display_product_card(product_row, categories_df)

    st.markdown("---")
    btn_update = st.button("🔧 Update Price")
    btn_history = st.button("📜 View Price History")

    if btn_update:
        with st.expander("Update Price (password required)", expanded=True):
            pw = st.text_input("Enter update password", type="password")
            if pw:
                if pw == update_password:
                    st.success("Password accepted. Enter new price below.")
                    new_price = st.number_input("New Price (₦)", min_value=0.0, value=float(product_row.get("current_price") or 0))
                    who_options = ["Mom", "You", "Sibling1", "Sibling2", "Sibling3"]
                    who = st.selectbox("Who is updating?", who_options, index=1)
                    note = st.text_area("Note (optional)", height=80)
                    if st.button("Save price change"):
                        old_price = product_row.get("current_price")
                        try:
                            update_price(product_id=sel_id, old_price=old_price, new_price=new_price, updated_by=who, note=note)
                            st.success(f"Price updated from ₦{old_price} to ₦{new_price}")
                            st.experimental_rerun()
                        except Exception as e:
                            st.error("Failed to update price. Check Supabase policies and keys.")
                            st.exception(e)
                else:
                    st.error("Access denied: wrong password.")

    if btn_history:
        st.subheader("Price History")
        ph = history_df[history_df['product_id'] == sel_id].copy()
        if ph.empty:
            st.info("No history available for this product yet.")
        else:
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

# ---------- ADMIN panel ----------
st.markdown("---")
with st.expander("Admin (change shared password / add product)", expanded=False):
    st.write("To change the shared update password or add basic product rows. Protected by the current shared password.")
    admin_pw = st.text_input("Enter current shared password", type="password")
    if admin_pw:
        if admin_pw == update_password:
            st.success("Access granted.")
            # Change password
            st.markdown("#### Change shared update password")
            new_pw = st.text_input("New password (leave empty to keep current)", type="password", key="new_pw")
            if st.button("Change password"):
                if new_pw:
                    change_shared_password(new_pw)
                    st.success("Password changed. Please Refresh (use sidebar).")
                else:
                    st.info("No new password entered.")
            # Quick add product
            st.markdown("#### Add a quick product")
            pname = st.text_input("Product name", key="pname")
            pcat = st.selectbox("Category", categories_df['name'].tolist() if not categories_df.empty else ["Uncategorized"])
            punit = st.text_input("Unit (e.g. 1kg, Pack of 1)", value="Pack of 1")
            pprice = st.number_input("Price (₦)", min_value=0.0, value=0.0)
            pimg = st.text_input("Image URL (optional)")
            if st.button("Add product"):
                # find category id
                cat_id = categories_df[categories_df['name'] == pcat]['id'].iloc[0] if not categories_df.empty else None
                supabase.table("products").insert({
                    "name": pname,
                    "category_id": int(cat_id) if cat_id is not None else None,
                    "unit": punit,
                    "current_price": pprice,
                    "image_url": pimg,
                    "last_updated": datetime.utcnow().isoformat(),
                    "updated_by": "Admin"
                }).execute()
                st.success("Product added. Please Refresh.")
        else:
            st.error("Access denied: wrong password.")

import streamlit as st
import pandas as pd
import datetime
import io
import os
import base64
from pymongo import MongoClient

# MongoDB setup
MONGO_URI = "mongodb+srv://myAtlasDBUser:root@myatlasclusteredu.78toh.mongodb.net/?retryWrites=true&w=majority&appName=myAtlasClusterEDU"
client = MongoClient(MONGO_URI)
db = client["Inventory"]
inventory_col = db["inventory"]
usage_col = db["usage"]
bills_col = db["bills"]

# Helper functions
def fetch_df(col, columns):
    data = list(col.find({}, {"_id": 0}))
    return pd.DataFrame(data) if data else pd.DataFrame(columns=columns)

def save_df(df, col):
    col.delete_many({})
    if not df.empty:
        col.insert_many(df.to_dict("records"))

# Initialize DataFrames
inv_columns = ["S.No", "Item Name", "Category", "Quantity", "Last Updated", "Location"]
usage_columns = ["Date", "Item Name", "Quantity", "Purpose", "Used In"]
bills_columns = ["Date", "Vendor", "Bill ID", "Items", "Filename"]

inv_df = fetch_df(inventory_col, inv_columns)
usage_df = fetch_df(usage_col, usage_columns)
bills_df = fetch_df(bills_col, bills_columns)

# Streamlit UI
st.set_page_config(layout="wide", page_title="Inventory App", page_icon="📦")
st.title("📦 Inventory Management System")
tab1, tab2, tab3, tab4 = st.tabs(["📋 Inventory", "🧾 Bills", "🛠️ Usage", "📊 Reports"])

# ===== Inventory Tab =====
with tab1:
    st.header("📋 View / Add / Update Inventory")

    with st.expander("🔍 View Inventory"):
        search = st.text_input("Search Item Name")
        filtered = inv_df.copy()
        if not filtered.empty:
            if search:
                filtered = filtered[filtered["Item Name"].str.lower().str.contains(search.lower())]
            filtered = filtered.drop(columns=["S.No"], errors="ignore")
            filtered.insert(0, "S.No", range(1, len(filtered) + 1))
        st.dataframe(filtered, use_container_width=True)

    with st.expander("➕ Add New Component"):
        with st.form("add_component"):
            name = st.text_input("Item Name", placeholder="e.g. Resistor")
            category = st.text_input("Category", placeholder="e.g. Electronics")
            qty = st.number_input("Quantity", min_value=0, step=1)
            location = st.text_input("Location", placeholder="e.g. Rack 3B")
            submitted = st.form_submit_button("Add")
            if submitted:
                sno = int(inv_df["S.No"].max()) + 1 if not inv_df.empty else 1
                row = {
                    "S.No": sno,
                    "Item Name": name,
                    "Category": category,
                    "Quantity": qty,
                    "Last Updated": str(datetime.date.today()),
                    "Location": location
                }
                inv_df = pd.concat([inv_df, pd.DataFrame([row])], ignore_index=True)
                save_df(inv_df, inventory_col)

                usage_log = {
                    "Date": str(datetime.date.today()),
                    "Item Name": name,
                    "Quantity": qty,
                    "Purpose": "Added",
                    "Used In": "-"
                }
                usage_df = pd.concat([usage_df, pd.DataFrame([usage_log])], ignore_index=True)
                save_df(usage_df, usage_col)

                st.success("Component added.")

    with st.expander("✏️ Update Component"):
        if not inv_df.empty:
            selected = st.selectbox("Select Item", inv_df["Item Name"].tolist())
            row = inv_df[inv_df["Item Name"] == selected].iloc[0]
            with st.form("update_component"):
                new_qty = st.number_input("Quantity", value=int(row["Quantity"]))
                new_cat = st.text_input("Category", value=row["Category"])
                new_loc = st.text_input("Location", value=row["Location"])
                update = st.form_submit_button("Update")
                if update:
                    inv_df.loc[inv_df["Item Name"] == selected, ["Quantity", "Category", "Location", "Last Updated"]] = [
                        new_qty, new_cat, new_loc, str(datetime.date.today())
                    ]
                    save_df(inv_df, inventory_col)
                    st.success("Component updated.")

# ===== Bills Tab =====
with tab2:
    st.header("🧾 Upload & Manage Bills")

    upload_method = st.radio("Choose Upload Method", ["Upload File", "Camera"])
    img_bytes = None

    if upload_method == "Upload File":
        file = st.file_uploader("Upload Bill (JPG or PNG)", type=["jpg", "png"])
        if file:
            img_bytes = file.read()
    else:
        cam = st.camera_input("Capture Bill Image")
        if cam:
            img_bytes = cam.read()

    vendor = st.text_input("Vendor Name")
    linked_items = st.multiselect("Linked Items", inv_df["Item Name"].tolist())

    if img_bytes and vendor and linked_items and st.button("📤 Save Bill"):
        from PIL import Image
        from fpdf import FPDF
        import io
        import os

        # Create readable filename
        safe_vendor = vendor.replace(" ", "_")
        safe_item = "_".join([item.replace(" ", "_") for item in linked_items])[:50]  # limit length
        today = datetime.datetime.now().strftime("%Y%m%d")
        filename = f"bills/{safe_vendor}_{safe_item}_{today}.pdf"

        # Ensure folder
        os.makedirs("bills", exist_ok=True)

        # Convert image to PDF
        image = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        image.save(filename, "PDF")

        # Add to bills_df
        new_entry = {
            "Date": str(datetime.date.today()),
            "Vendor": vendor,
            "Bill ID": len(bills_df) + 1,
            "Items": ", ".join(linked_items),
            "Filename": filename
        }

        bills_df = pd.concat([bills_df, pd.DataFrame([new_entry])], ignore_index=True)
        save_df(bills_df, bills_col)

        st.success(f"✅ Bill saved as `{os.path.basename(filename)}`")

    # Show saved bills
    st.subheader("📄 View Saved Bills")
    if not bills_df.empty:
        bills_df_display = bills_df.copy()
        bills_df_display.insert(0, "Sl", range(1, len(bills_df_display) + 1))
        st.dataframe(bills_df_display[["Sl", "Date", "Vendor", "Bill ID", "Items", "Filename"]], use_container_width=True)

        selected_file = st.selectbox("Select a bill to view", bills_df["Filename"].tolist())

        if selected_file and st.button("👁️ View Selected Bill"):
            if os.path.exists(selected_file):
                with open(selected_file, "rb") as f:
                    base64_pdf = base64.b64encode(f.read()).decode("utf-8")
                    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="700" height="500"></iframe>'
                    st.markdown(pdf_display, unsafe_allow_html=True)
                    st.download_button("📥 Download Bill PDF", data=open(selected_file, "rb"), file_name=os.path.basename(selected_file))
            else:
                st.error("Selected file not found.")
    else:
        st.info("No bills uploaded yet.")
# ===== Usage Tab =====
with tab3:
    st.header("🛠️ Usage Logging")
    if inv_df.empty:
        st.warning("Inventory is empty.")
    else:
        with st.form("usage_form"):
            item = st.selectbox("Used Item", inv_df["Item Name"].tolist())
            qty = st.number_input("Used Quantity", min_value=1)
            purpose = st.text_input("Purpose")
            used_in = st.text_input("Used In")
            if st.form_submit_button("Log Usage"):
                usage = {
                    "Date": str(datetime.date.today()),
                    "Item Name": item,
                    "Quantity": qty,
                    "Purpose": purpose,
                    "Used In": used_in
                }
                usage_df = pd.concat([usage_df, pd.DataFrame([usage])], ignore_index=True)
                save_df(usage_df, usage_col)
                inv_df.loc[inv_df["Item Name"] == item, "Quantity"] -= qty
                save_df(inv_df, inventory_col)
                st.success("Usage logged.")

    st.dataframe(usage_df, use_container_width=True)

# ===== Reports Tab =====
with tab4:
    st.header("📊 Reports")
    col1, col2, col3 = st.columns(3)
    col1.metric("📦 Components", len(inv_df))
    col2.metric("🔢 Total Qty", inv_df["Quantity"].sum() if not inv_df.empty else 0)
    col3.metric("⚠️ Below Min", (inv_df["Quantity"] < 10).sum() if not inv_df.empty else 0)

    st.download_button("Download Inventory", inv_df.to_csv(index=False), "inventory.csv")
    st.download_button("Download Usage Log", usage_df.to_csv(index=False), "usage_log.csv")
    st.download_button("Download Bill Log", bills_df.to_csv(index=False), "bills_log.csv")

    if not inv_df.empty:
        st.subheader("Top Stocked Items")
        top_items = inv_df.sort_values(by="Quantity", ascending=False).head(10)
        st.bar_chart(top_items.set_index("Item Name")["Quantity"])

        st.subheader("Restock Suggestions")
        low = inv_df[inv_df["Quantity"] < 10].copy()
        low["Suggested Restock"] = 20 - low["Quantity"]
        st.dataframe(low[["Item Name", "Quantity", "Suggested Restock"]], use_container_width=True)

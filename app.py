import streamlit as st
import pandas as pd
import datetime
import io
from pymongo import MongoClient
from PIL import Image

# MongoDB Connection
MONGO_URI = "mongodb+srv://myAtlasDBUser:root@myatlasclusteredu.78toh.mongodb.net/?retryWrites=true&w=majority&appName=myAtlasClusterEDU"
client = MongoClient(MONGO_URI)
db = client["Inventory"]
inventory_col = db["inventory"]
usage_col = db["usage"]
bills_col = db["bills"]

# Helper Functions
def fetch_df(col, default_columns):
    data = list(col.find({}, {"_id": 0}))
    if not data:
        return pd.DataFrame(columns=default_columns)
    return pd.DataFrame(data)

def save_df(df, col):
    col.delete_many({})
    if not df.empty:
        col.insert_many(df.to_dict("records"))

# Initial DataFrames
inv_columns = ["S.No", "Item Name", "Category", "Quantity", "Min Stock", "Last Updated", "Location"]
usage_columns = ["Date", "Item Name", "Quantity", "Purpose", "Used In"]
bills_columns = ["Date", "Vendor", "Bill ID", "Items", "Filename"]

inv_df = fetch_df(inventory_col, inv_columns)
usage_df = fetch_df(usage_col, usage_columns)
bills_df = fetch_df(bills_col, bills_columns)

# Streamlit UI
st.set_page_config(layout="wide", page_title="Inventory Manager", page_icon="📦")
st.title("Inventory System")
tab1, tab2, tab3, tab4 = st.tabs(["📋 Inventory", "🧾 Bill Scanner", "🛠️ Usage", "📊 Reports"])

# ======= Inventory Tab =======
with tab1:
    st.header("📋 View / Add / Update Components")
    
    with st.expander("👁️ View Inventory Table"):
        search_term = st.text_input("Search Item Name", placeholder="e.g. 5v Resistor,Chip name...")
        show_low = st.checkbox("Show Below Min Stock")
        sort_options = [col for col in ["S.No", "Item Name", "Quantity"] if col in inv_df.columns]
        sort_by = st.selectbox("Sort by", sort_options) if sort_options else None

        filtered = inv_df.copy()
        if not filtered.empty:
            if search_term:
                filtered = filtered[filtered["Item Name"].str.lower().str.contains(search_term.lower())]
            if show_low:
                filtered = filtered[filtered["Quantity"] < filtered["Min Stock"]]
            if sort_by:
                filtered = filtered.sort_values(by=sort_by)

        st.dataframe(filtered, use_container_width=True)

    with st.expander("➕ Add New Component"):
        with st.form("add_form"):
            name = st.text_input("Item Name", placeholder="e.g. 5v Resistor")
            category = st.text_input("Category", placeholder="e.g. Resistor")
            qty = st.number_input("Quantity", min_value=0, step=1)
            location = st.text_input("Location", placeholder="e.g. Shelf B1")

            if st.form_submit_button("✅ Add"):
                new_sno = int(inv_df["S.No"].max()) + 1 if not inv_df.empty else 1
                new_row = {
                    "S.No": new_sno,
                    "Item Name": name,
                    "Category": category,
                    "Quantity": qty,
                    "Min Stock": 10,  # Default internal value
                    "Last Updated": str(datetime.date.today()),
                    "Location": location
                }
                inv_df = pd.concat([inv_df, pd.DataFrame([new_row])], ignore_index=True)
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

                st.success("✅ Component added.")

    with st.expander("✏️ Update Component"):
        if not inv_df.empty:
            selected = st.selectbox("Select item", inv_df["Item Name"].tolist())
            row = inv_df[inv_df["Item Name"] == selected].iloc[0]

            with st.form("update_form"):
                qty = st.number_input("New Quantity", value=int(row["Quantity"]))
                category = st.text_input("New Category", value=row["Category"], placeholder="e.g. Electrical")
                location = st.text_input("New Location", value=row["Location"], placeholder="e.g. Rack A-2")

                if st.form_submit_button("🔁 Update"):
                    inv_df.loc[inv_df["Item Name"] == selected, ["Quantity", "Category", "Location", "Last Updated"]] = [
                        qty, category, location, str(datetime.date.today())
                    ]
                    save_df(inv_df, inventory_col)
                    st.success("✅ Updated.")

# ======= Bill Scanner Tab =======
with tab2:
    st.header("🧾 Scan and Save Bill")
    method = st.radio("Upload Method", ["Upload", "Camera"])
    img_bytes = None

    if method == "Upload":
        file = st.file_uploader("Upload Image", type=["jpg", "png"])
        if file:
            img_bytes = file.read()
    else:
        cam = st.camera_input("Take Photo")
        if cam:
            img_bytes = cam.read()

    vendor = st.text_input("Vendor", placeholder="e.g. ABC Suppliers")
    linked_items = st.multiselect("Linked Items", inv_df["Item Name"].tolist() if "Item Name" in inv_df.columns else [])

    if img_bytes and st.button("📤 Save Bill"):
        filename = f"bill_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        img = Image.open(io.BytesIO(img_bytes))
        img.save(filename, "PDF")

        new_bill = {
            "Date": str(datetime.date.today()),
            "Vendor": vendor,
            "Bill ID": len(bills_df) + 1,
            "Items": ", ".join(linked_items),
            "Filename": filename
        }
        bills_df = pd.concat([bills_df, pd.DataFrame([new_bill])], ignore_index=True)
        save_df(bills_df, bills_col)

        st.success("✅ Bill saved.")

    st.subheader("📄 Saved Bills")
    st.dataframe(bills_df, use_container_width=True)

# ======= Usage Tab =======
with tab3:
    st.header("🛠️ Usage Log")
    if inv_df.empty:
        st.warning("⚠️ No inventory data found.")
    else:
        with st.form("usage_form"):
            used_item = st.selectbox("Used Item", inv_df["Item Name"].tolist())
            used_qty = st.number_input("Quantity Used", min_value=1)
            purpose = st.text_input("Purpose", placeholder="e.g. Maintenance")
            used_in = st.text_input("Used In", placeholder="e.g. Machine A")

            if st.form_submit_button("Log Usage"):
                log = {
                    "Date": str(datetime.date.today()),
                    "Item Name": used_item,
                    "Quantity": used_qty,
                    "Purpose": purpose,
                    "Used In": used_in
                }
                usage_df = pd.concat([usage_df, pd.DataFrame([log])], ignore_index=True)
                save_df(usage_df, usage_col)

                inv_df.loc[inv_df["Item Name"] == used_item, "Quantity"] -= used_qty
                save_df(inv_df, inventory_col)

                st.success("✅ Usage logged.")

    st.dataframe(usage_df, use_container_width=True)

# ======= Reports Tab =======
with tab4:
    st.header("📊 Reports")

    col1, col2, col3 = st.columns(3)
    col1.metric("📦 Components", len(inv_df))
    col2.metric("🔢 Total Qty", inv_df["Quantity"].sum() if not inv_df.empty else 0)
    col3.metric("⚠️ Below Min", (inv_df["Quantity"] < inv_df["Min Stock"]).sum() if not inv_df.empty else 0)

    st.download_button("⬇️ Download Inventory", inv_df.to_csv(index=False), "inventory.csv")
    st.download_button("⬇️ Download Usage Log", usage_df.to_csv(index=False), "usage_log.csv")
    st.download_button("⬇️ Download Bill Logs", bills_df.to_csv(index=False), "bills_log.csv")

    if not inv_df.empty:
        st.subheader("Top Stocked Items")
        top = inv_df.sort_values(by="Quantity", ascending=False).head(10)
        st.bar_chart(top.set_index("Item Name")["Quantity"])

        st.subheader("Reorder Suggestions")
        low = inv_df[inv_df["Quantity"] < inv_df["Min Stock"]].copy()
        low["Suggested Reorder"] = low["Min Stock"] * 2 - low["Quantity"]
        st.dataframe(low[["Item Name", "Quantity", "Min Stock", "Suggested Reorder"]], use_container_width=True)

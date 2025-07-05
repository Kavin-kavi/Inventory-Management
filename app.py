import streamlit as st
import pandas as pd
import datetime
import os
from scanner_utils import auto_crop_bill
from fpdf import FPDF

INVENTORY_FILE = "inventory.xlsx"
USAGE_LOG_FILE = "usage_log.xlsx"
BILLS_LOG_FILE = "bills_log.xlsx"
SCAN_DIR = "scanned_bills"
os.makedirs(SCAN_DIR, exist_ok=True)

def init_file(path, columns):
    if not os.path.exists(path):
        pd.DataFrame(columns=columns).to_excel(path, index=False)

init_file(INVENTORY_FILE, ["S.No", "Item Name", "Category", "Quantity", "Min Stock", "Last Updated", "Location"])
init_file(USAGE_LOG_FILE, ["Date", "Item Name", "Quantity", "Purpose", "Used In"])
init_file(BILLS_LOG_FILE, ["Date", "Vendor", "Bill ID", "Items", "Filename"])

def load_df(file): return pd.read_excel(file)
def save_df(df, file): df.to_excel(file, index=False)

st.set_page_config(layout="wide", page_title="Inventory Manager", page_icon="📦")
st.title("📦 Loom Component Inventory System")

# Mobile responsive CSS
st.markdown("""
<style>
@media only screen and (max-width: 768px) {
    section.main > div {flex-direction: column !important;}
    .css-1v0mbdj {width: 100% !important;}
}
</style>
""", unsafe_allow_html=True)

tab1, tab2, tab3, tab4 = st.tabs(["📋 Inventory", "🧾 Bill Scanner", "🛠️ Usage", "📊 Reports"])

# ==== Inventory Tab ====
with tab1:
    st.header("📋 View / Add / Update Components")
    inv_df = load_df(INVENTORY_FILE)
    inv_df = inv_df.sort_values(by="S.No").reset_index(drop=True)

    with st.expander("👁️ View Inventory Table"):
        col1, col2 = st.columns([2, 1])
        with col1:
            search_term = st.text_input("🔍 Search by Item Name")
        with col2:
            show_low = st.checkbox("⚠️ Show only below min stock")

        sort_by = st.selectbox("Sort by", ["S.No", "Item Name", "Quantity"])
        filtered_df = inv_df

        if search_term:
            search_term = search_term.lower()
            filtered_df = filtered_df[filtered_df["Item Name"].str.lower().str.contains(search_term)]
        if show_low:
            filtered_df = filtered_df[filtered_df["Quantity"] < filtered_df["Min Stock"]]

        filtered_df = filtered_df.sort_values(by=sort_by)

        def highlight_low(row):
            return ['background-color: red; color: white' if row['Quantity'] < row['Min Stock'] else '' for _ in row]

        st.dataframe(filtered_df.style.apply(highlight_low, axis=1), use_container_width=True, hide_index=True)

    with st.expander("➕ Add New Component"):
        with st.form("add_form"):
            name = st.text_input("Item Name", placeholder="e.g., Motor Controller")
            category = st.text_input("Category", placeholder="e.g., Electrical")
            qty = st.number_input("Quantity", min_value=0, step=1)
            location = st.text_input("Location", placeholder="e.g., Rack 3, Section B")

            if st.form_submit_button("✅ Add"):
                new_sno = inv_df["S.No"].max() + 1 if not inv_df.empty else 1
                new_row = {
                    "S.No": new_sno,
                    "Item Name": name,
                    "Category": category,
                    "Quantity": qty,
                    "Min Stock": 10,
                    "Last Updated": datetime.date.today(),
                    "Location": location
                }
                inv_df = pd.concat([inv_df, pd.DataFrame([new_row])], ignore_index=True)
                save_df(inv_df, INVENTORY_FILE)

                log_df = load_df(USAGE_LOG_FILE)
                log_df = pd.concat([log_df, pd.DataFrame([{
                    "Date": datetime.date.today(),
                    "Item Name": name,
                    "Quantity": qty,
                    "Purpose": "Added",
                    "Used In": "-"
                }])], ignore_index=True)
                save_df(log_df, USAGE_LOG_FILE)

                st.success("✅ Component added successfully.")

    with st.expander("✏️ Update Component"):
        with st.form("update_form"):
            selected = st.selectbox("Select item to update", inv_df["Item Name"].tolist())
            row = inv_df[inv_df["Item Name"] == selected].iloc[0]

            qty = st.number_input("New Quantity", value=int(row["Quantity"]))
            category = st.text_input("New Category", value=row["Category"])
            location = st.text_input("New Location", value=row["Location"])

            if st.form_submit_button("🔁 Update"):
                inv_df.loc[inv_df["Item Name"] == selected, ["Quantity", "Category", "Location", "Last Updated"]] = [
                    qty, category, location, datetime.date.today()
                ]
                save_df(inv_df, INVENTORY_FILE)

                log_df = load_df(USAGE_LOG_FILE)
                log_df = pd.concat([log_df, pd.DataFrame([{
                    "Date": datetime.date.today(),
                    "Item Name": selected,
                    "Quantity": qty,
                    "Purpose": "Updated",
                    "Used In": "-"
                }])], ignore_index=True)
                save_df(log_df, USAGE_LOG_FILE)

                st.success("✅ Component updated.")

# ==== Bill Scanner ====
with tab2:
    st.header("🧾 Scan Bill and Save")
    opt = st.radio("Upload Method", ["Upload Image", "Use Camera"])
    image_data = None

    if opt == "Upload Image":
        img = st.file_uploader("Upload Bill Image", type=["jpg", "jpeg", "png"])
        if img: image_data = img.read()
    else:
        cam = st.camera_input("Take Photo")
        if cam: image_data = cam.read()

    vendor = st.text_input("Vendor Name")
    link_items = st.multiselect("Linked Items", inv_df["Item Name"].tolist())

    if image_data and st.button("📤 Save Bill"):
        filename = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        raw_path = f"{SCAN_DIR}/{filename}.jpg"
        with open(raw_path, "wb") as f: f.write(image_data)

        processed = auto_crop_bill(raw_path)
        temp_path = f"{SCAN_DIR}/temp.jpg"
        cv2.imwrite(temp_path, processed)

        pdf_path = f"{SCAN_DIR}/{filename}.pdf"
        pdf = FPDF()
        pdf.add_page()
        pdf.image(temp_path, x=10, y=10, w=190)
        pdf.output(pdf_path)
        os.remove(temp_path)

        bill_df = load_df(BILLS_LOG_FILE)
        bill_df = pd.concat([bill_df, pd.DataFrame([{
            "Date": datetime.date.today(),
            "Vendor": vendor,
            "Bill ID": len(bill_df) + 1,
            "Items": ", ".join(link_items),
            "Filename": os.path.basename(pdf_path)
        }])], ignore_index=True)
        save_df(bill_df, BILLS_LOG_FILE)
        st.success("✅ Bill saved as PDF")

    st.subheader("📄 Saved Bills")
    st.dataframe(load_df(BILLS_LOG_FILE), use_container_width=True, hide_index=True)

# ==== Usage Tab ====
with tab3:
    st.header("🛠️ Usage Log")
    usage_df = load_df(USAGE_LOG_FILE)

    with st.form("usage_form"):
        used_item = st.selectbox("Used Item", inv_df["Item Name"].tolist())
        used_qty = st.number_input("Quantity Used", min_value=1)
        purpose = st.text_input("Purpose")
        used_in = st.text_input("Used In")

        if st.form_submit_button("Log Usage"):
            new = {
                "Date": datetime.date.today(),
                "Item Name": used_item,
                "Quantity": used_qty,
                "Purpose": purpose,
                "Used In": used_in
            }
            usage_df = pd.concat([usage_df, pd.DataFrame([new])], ignore_index=True)
            save_df(usage_df, USAGE_LOG_FILE)

            inv_df.loc[inv_df["Item Name"] == used_item, "Quantity"] -= used_qty
            save_df(inv_df, INVENTORY_FILE)

            st.success("✅ Usage logged and stock updated.")

    st.dataframe(usage_df, use_container_width=True, hide_index=True)

# ==== Reports Tab ====
with tab4:
    st.header("📊 Reports & Summary")
    col1, col2, col3 = st.columns(3)
    col1.metric("📦 Total Components", len(inv_df))
    col2.metric("🔢 Total Quantity", inv_df["Quantity"].sum())
    col3.metric("⚠️ Below Min", (inv_df["Quantity"] < inv_df["Min Stock"]).sum())

    with st.expander("📅 Filter Usage by Date"):
        start_date = st.date_input("Start Date", value=datetime.date.today() - datetime.timedelta(days=30))
        end_date = st.date_input("End Date", value=datetime.date.today())
        usage_filtered = usage_df[
            (pd.to_datetime(usage_df["Date"]) >= pd.to_datetime(start_date)) &
            (pd.to_datetime(usage_df["Date"]) <= pd.to_datetime(end_date))
        ]
        st.dataframe(usage_filtered, use_container_width=True)

    st.download_button("⬇️ Download Inventory", inv_df.to_csv(index=False), "inventory.csv")
    st.download_button("⬇️ Download Usage Log", usage_df.to_csv(index=False), "usage_log.csv")
    st.download_button("⬇️ Download Bill Logs", load_df(BILLS_LOG_FILE).to_csv(index=False), "bills_log.csv")

    st.markdown("### 🔝 Top Stocked Items")
    top = inv_df.sort_values(by="Quantity", ascending=False).head(10)
    st.bar_chart(top.set_index("Item Name")["Quantity"])

    st.markdown("### 🧠 Reorder Suggestions")
    low_items = inv_df[inv_df["Quantity"] < inv_df["Min Stock"]]
    suggestions = low_items.copy()
    suggestions["Suggested Reorder"] = suggestions["Min Stock"] * 2 - suggestions["Quantity"]
    st.dataframe(suggestions[["Item Name", "Quantity", "Min Stock", "Suggested Reorder"]], use_container_width=True, hide_index=True)


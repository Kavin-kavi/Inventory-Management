import streamlit as st
import pandas as pd
import datetime
import io
import cv2
import numpy as np
from pymongo import MongoClient
from PIL import Image
from fpdf import FPDF
import os

# MongoDB Setup
MONGO_URI = "mongodb+srv://myAtlasDBUser:root@myatlasclusteredu.78toh.mongodb.net/?retryWrites=true&w=majority"
client = MongoClient(MONGO_URI)
db = client["Inventory"]
inventory_col = db["inventory"]
usage_col = db["usage"]
bills_col = db["bills"]

# Helper Functions
def fetch_df(col, default_cols):
    data = list(col.find({}, {"_id": 0}))
    return pd.DataFrame(data) if data else pd.DataFrame(columns=default_cols)

def save_df(df, col):
    col.delete_many({})
    if not df.empty:
        col.insert_many(df.to_dict("records"))

def enhance_and_crop(img_bytes):
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    np_img = np.array(img)
    gray = cv2.cvtColor(np_img, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blurred, 50, 200)

    contours, _ = cv2.findContours(edged.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    if contours:
        peri = cv2.arcLength(contours[0], True)
        approx = cv2.approxPolyDP(contours[0], 0.02 * peri, True)
        if len(approx) == 4:
            pts = approx.reshape(4, 2)
            rect = order_points(pts)
            (tl, tr, br, bl) = rect

            widthA = np.linalg.norm(br - bl)
            widthB = np.linalg.norm(tr - tl)
            heightA = np.linalg.norm(tr - br)
            heightB = np.linalg.norm(tl - bl)

            maxWidth = max(int(widthA), int(widthB))
            maxHeight = max(int(heightA), int(heightB))

            dst = np.array([[0, 0], [maxWidth - 1, 0], [maxWidth - 1, maxHeight - 1], [0, maxHeight - 1]], dtype="float32")
            M = cv2.getPerspectiveTransform(rect, dst)
            warped = cv2.warpPerspective(np_img, M, (maxWidth, maxHeight))
        else:
            warped = np_img
    else:
        warped = np_img

    enhanced = cv2.cvtColor(warped, cv2.COLOR_RGB2GRAY)
    enhanced = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 11, 10)
    return Image.fromarray(enhanced)

def order_points(pts):
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1)

    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]

    return rect

# Column Defaults
inv_cols = ["S.No", "Item Name", "Category", "Quantity", "Last Updated", "Location"]
usage_cols = ["Date", "Item Name", "Quantity", "Purpose", "Used In"]
bills_cols = ["Date", "Vendor", "Bill ID", "Items", "Filename"]

# Load DataFrames
inv_df = fetch_df(inventory_col, inv_cols)
usage_df = fetch_df(usage_col, usage_cols)
bills_df = fetch_df(bills_col, bills_cols)

# Streamlit UI Setup
st.set_page_config(layout="wide", page_title="Inventory Manager", page_icon="📦")
st.title("📦 Inventory System")
tab1, tab2, tab3, tab4 = st.tabs(["📋 Inventory", "🧾 Bill Scanner", "🛠️ Usage", "📊 Reports"])

# === Tab 1: Inventory ===
with tab1:
    st.header("📋 View / Add / Update Components")

    with st.expander("👁️ View Inventory Table"):
        search = st.text_input("Search Item Name", placeholder="Search by name...")
        show_low = st.checkbox("Show items below stock")
        sort_col = st.selectbox("Sort by", ["S.No", "Item Name", "Quantity"]) if not inv_df.empty else None

        filtered = inv_df.copy()
        if search:
            filtered = filtered[filtered["Item Name"].str.lower().str.contains(search.lower())]
        if show_low:
            filtered = filtered[filtered["Quantity"] < 10]
        if sort_col:
            filtered = filtered.sort_values(by=sort_col)

        st.dataframe(filtered, use_container_width=True)

    with st.expander("➕ Add New Component"):
        with st.form("add_form"):
            name = st.text_input("Item Name", placeholder="e.g. 5v Resistor")
            category = st.text_input("Category", placeholder="e.g. Electrical")
            qty = st.number_input("Quantity", min_value=0, step=1)
            location = st.text_input("Location", placeholder="e.g. Rack 4A")

            if st.form_submit_button("✅ Add"):
                new_sno = int(inv_df["S.No"].max()) + 1 if not inv_df.empty else 1
                row = {
                    "S.No": new_sno,
                    "Item Name": name,
                    "Category": category,
                    "Quantity": qty,
                    "Last Updated": str(datetime.date.today()),
                    "Location": location
                }
                inv_df = pd.concat([inv_df, pd.DataFrame([row])], ignore_index=True)
                save_df(inv_df, inventory_col)

                log = {
                    "Date": str(datetime.date.today()),
                    "Item Name": name,
                    "Quantity": qty,
                    "Purpose": "Added",
                    "Used In": "-"
                }
                usage_df = pd.concat([usage_df, pd.DataFrame([log])], ignore_index=True)
                save_df(usage_df, usage_col)

                st.success("✅ Added.")

    with st.expander("✏️ Update Component"):
        if not inv_df.empty:
            selected = st.selectbox("Select Item", inv_df["Item Name"])
            row = inv_df[inv_df["Item Name"] == selected].iloc[0]

            with st.form("update_form"):
                qty = st.number_input("New Quantity", value=int(row["Quantity"]))
                category = st.text_input("New Category", value=row["Category"])
                location = st.text_input("New Location", value=row["Location"])
                if st.form_submit_button("🔁 Update"):
                    inv_df.loc[inv_df["Item Name"] == selected, ["Quantity", "Category", "Location", "Last Updated"]] = [
                        qty, category, location, str(datetime.date.today())
                    ]
                    save_df(inv_df, inventory_col)
                    st.success("✅ Updated.")

# === Tab 2: Bill Scanner ===
with tab2:
    st.header("🧾 Scan and Save Bill")
    method = st.radio("Select Input", ["Upload", "Camera"])
    img_bytes = None

    if method == "Upload":
        file = st.file_uploader("Upload Bill Image", type=["jpg", "jpeg", "png"])
        if file:
            img_bytes = file.read()
    else:
        cam = st.camera_input("Capture Bill")
        if cam:
            img_bytes = cam.read()

    vendor = st.text_input("Vendor Name", placeholder="e.g. ABC Supplies")
    linked = st.multiselect("Linked Items", inv_df["Item Name"].tolist())

    if img_bytes and st.button("📤 Save Bill"):
        scanned = enhance_and_crop(img_bytes)
        filename = f"bill_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        scanned.save(filename, "PDF")

        new_row = {
            "Date": str(datetime.date.today()),
            "Vendor": vendor,
            "Bill ID": len(bills_df) + 1,
            "Items": ", ".join(linked),
            "Filename": filename
        }
        bills_df = pd.concat([bills_df, pd.DataFrame([new_row])], ignore_index=True)
        save_df(bills_df, bills_col)

        st.image(scanned, caption="Scanned Preview", use_column_width=True)
        with open(filename, "rb") as f:
            st.download_button("⬇️ Download PDF", f, file_name=filename, mime="application/pdf")

        st.success("✅ Bill saved.")

    st.subheader("📄 Saved Bills")
    st.dataframe(bills_df, use_container_width=True)

# === Tab 3: Usage Log ===
with tab3:
    st.header("🛠️ Usage Log")
    if inv_df.empty:
        st.warning("Inventory is empty.")
    else:
        with st.form("usage_form"):
            used_item = st.selectbox("Used Item", inv_df["Item Name"])
            qty_used = st.number_input("Quantity Used", min_value=1)
            purpose = st.text_input("Purpose", placeholder="e.g. Maintenance")
            used_in = st.text_input("Used In", placeholder="e.g. Machine A")

            if st.form_submit_button("Log Usage"):
                log = {
                    "Date": str(datetime.date.today()),
                    "Item Name": used_item,
                    "Quantity": qty_used,
                    "Purpose": purpose,
                    "Used In": used_in
                }
                usage_df = pd.concat([usage_df, pd.DataFrame([log])], ignore_index=True)
                save_df(usage_df, usage_col)

                inv_df.loc[inv_df["Item Name"] == used_item, "Quantity"] -= qty_used
                save_df(inv_df, inventory_col)
                st.success("✅ Usage logged.")

    st.dataframe(usage_df, use_container_width=True)

# === Tab 4: Reports ===
with tab4:
    st.header("📊 Reports")

    col1, col2, col3 = st.columns(3)
    col1.metric("📦 Components", len(inv_df))
    col2.metric("🔢 Total Qty", inv_df["Quantity"].sum() if not inv_df.empty else 0)
    col3.metric("⚠️ Below Min", (inv_df["Quantity"] < 10).sum() if not inv_df.empty else 0)

    st.download_button("⬇️ Inventory CSV", inv_df.to_csv(index=False), "inventory.csv")
    st.download_button("⬇️ Usage Log CSV", usage_df.to_csv(index=False), "usage_log.csv")
    st.download_button("⬇️ Bill Log CSV", bills_df.to_csv(index=False), "bills_log.csv")

    if not inv_df.empty:
        st.subheader("Top Stocked Items")
        top = inv_df.sort_values(by="Quantity", ascending=False).head(10)
        st.bar_chart(top.set_index("Item Name")["Quantity"])

        st.subheader("Reorder Suggestions")
        low = inv_df[inv_df["Quantity"] < 10].copy()
        low["Suggested Reorder"] = 20 - low["Quantity"]
        st.dataframe(low[["Item Name", "Quantity", "Suggested Reorder"]], use_container_width=True)

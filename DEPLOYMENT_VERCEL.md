# Step-by-Step Guide: Deploying Land Resurvey Portal on Vercel & MongoDB Atlas (100% Free)

This guide walks you through setting up a **free cloud MongoDB database** and hosting the **ResurveyUpdates Portal** on **Vercel** with automatic HTTPS and instant global access.

---

## Part 1: Create a Free MongoDB Atlas Database (3 minutes)

1. Go to [https://www.mongodb.com/cloud/atlas](https://www.mongodb.com/cloud/atlas) and click **Try Free**.
2. Sign up with your Google account or email.
3. When prompted to select a cluster plan:
   - Select **M0 Free** (512 MB storage — free forever, no credit card required).
   - Provider: **AWS** or **Google Cloud**.
   - Region: Select **Mumbai (ap-south-1)** for the lowest latency in India.
   - Click **Create Deployment**.
4. **Create Database User**:
   - Set a Username (e.g. `resurvey_admin`) and a secure Password (e.g. `ProjectAdmin@2026`).
   - Click **Create Database User**.
5. **Configure Network Access**:
   - In the "Where would you like to connect from?" section, select **Allow Access from Anywhere** (`0.0.0.0/0`) so Vercel can connect securely over TLS.
   - Click **Finish and Close**.
6. **Get your Connection String**:
   - Click **Connect** on your cluster overview page.
   - Select **Drivers** (Python).
   - Copy the connection URI. It will look like:
     ```text
     mongodb+srv://resurvey_admin:<password>@cluster0.abcde.mongodb.net/?retryWrites=true&w=majority
     ```
   - Replace `<password>` with the password you created in step 4.

---

## Part 2: Seed Baseline Data into MongoDB Atlas

Before deploying to Vercel, run the one-click seed script from your machine to populate all 32 districts and your baseline village survey data:

```bash
# In the project directory:
python seed_mongo.py "mongodb+srv://resurvey_admin:YOUR_PASSWORD@cluster0.abcde.mongodb.net/?retryWrites=true&w=majority"
```

You will see:
```text
Connecting to MongoDB...
Connected successfully!
Seeded 32 districts into 'resurvey_portal.districts'
Seeded 90 village records into 'resurvey_portal.villages'
Seeded 6 users into 'resurvey_portal.users'
MONGODB ATLAS SEEDING COMPLETED SUCCESSFULLY!
```

---

## Part 3: Push Project to GitHub

1. Open your terminal or Git bash inside `ResurveyUpdates`:
   ```bash
   git init
   git add .
   git commit -m "Initial commit: ResurveyUpdates Portal"
   ```
2. Create a new repository on [https://github.com/new](https://github.com/new) (e.g. `ResurveyUpdates`).
3. Link and push your code:
   ```bash
   git remote add origin https://github.com/YOUR_GITHUB_USERNAME/ResurveyUpdates.git
   git branch -M main
   git push -u origin main
   ```

---

## Part 4: Deploy on Vercel (2 minutes)

1. Go to [https://vercel.com](https://vercel.com) and click **Sign Up** (or Log in with your GitHub account).
2. On your Vercel Dashboard, click **Add New...** $\rightarrow$ **Project**.
3. Locate `ResurveyUpdates` in the list and click **Import**.
4. In the **Environment Variables** section, add:
   - **Key**: `MONGODB_URI`
   - **Value**: Your MongoDB Atlas connection string (e.g. `mongodb+srv://resurvey_admin:password@cluster0.abcde.mongodb.net/?retryWrites=true&w=majority`)
5. Click **Deploy**!
6. In ~30 to 45 seconds, Vercel will present you with your live URL:
   ```text
   https://ResurveyUpdates.vercel.app
   ```

Anyone with this URL can now open the dashboard on desktop, tablet, or phone!

---

## Part 5: User Access & Member Login Credentials

Members can log in by clicking the **Switch / Sign In** button on the top right of the dashboard:

| User Account | Username | Password | Role & Assigned District | Access Level |
| :--- | :--- | :--- | :--- | :--- |
| **Project Director** | `admin` | `admin` | Administrator (All Districts) | Can view, add, edit, and delete across all 32 districts. |
| **Asifabad Nodal Officer** | `asifabad_officer` | `pass` | Asifabad District | Can submit and update records for Asifabad. |
| **Nizamabad Nodal Officer** | `nizamabad_officer` | `pass` | Nizamabad District | Can submit and update records for Nizamabad. |
| **Medak Nodal Officer** | `medak_officer` | `pass` | Medak District | Can submit and update records for Medak. |
| **Siddipet Nodal Officer** | `siddipet_officer` | `pass` | Siddipet District | Can submit and update records for Siddipet. |
| **Public Auditor / Guest** | `viewer` | `guest` | Viewer (All Districts) | Read-only access to metrics, charts, and exports. |

---

## Part 6: Local Development & Offline Testing

To test and run the portal on your computer at any time:
```bash
# Run local server
.\.venv\Scripts\python.exe run_local.py
```
Open `http://127.0.0.1:8000` in your web browser.

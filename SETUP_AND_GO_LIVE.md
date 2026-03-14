# Copperline — Setup Guide

## What's Real and Working Right Now

| Component | Status | Notes |
|---|---|---|
| Lead pipeline CSV → emails | ✅ WORKS | Run the dashboard and click Discover + Draft |
| Industry-aware email copy | ✅ WORKS | Plumbers get plumber copy, HVAC gets HVAC copy, etc. |
| Email queue + approval | ✅ WORKS | Dashboard lets you review/edit/approve each email |
| Gmail sending | ✅ WORKS | Needs your app password set (already in README) |
| Email scraper (from websites) | ✅ WORKS | Clicks "Find Emails" button in dashboard |
| Auto-discovery (Google Places) | ✅ WORKS | Needs Google API key (5 min setup, free tier) |
| Demo: After-Hours Lead Capture | ✅ WORKS | Open demo file in browser — fully interactive |
| Demo: Appointment Reminder | ✅ WORKS | Open demo file — live ROI calculator, schedule |
| Demo: FAQ Chatbot | ✅ WORKS | Needs Anthropic API key to actually chat |

---



Double-click `Launch Dashboard.bat` from the OfficeAutomation folder.
Browser opens to http://localhost:5000 automatically.

---

## Step 4 — Your First Real Prospecting Run

1. In the dashboard: select **plumbing**, type **Rockford**, **IL**, limit **20**
2. Click **⚡ Discover + Draft**
3. Google Places finds 20 real plumbers in Rockford with their addresses/phones
4. Pipeline drafts industry-specific emails for each one
5. Click **📧 Find Emails** — scrapes their websites for contact emails
6. For any still missing emails: Google "[business name] Rockford IL email" and paste it in
7. Review each email, edit if needed, approve, send

---

## Step 5 — Demo Prep for Sales Calls

All three demos are in: `automation-agency-office/demos/`

| Demo | File | Who to show it to |
|---|---|---|
| After-Hours Lead Capture | `missed_call_capture/index.html` | Plumbers, HVAC, electricians |
| Appointment Reminder | `appointment_reminder/index.html` | Dentists, salons, auto shops, gyms |
| FAQ Chatbot | `faq_chatbot/index.html` | Any business with repetitive phone Q&A |

**To show them on a call:**
- Open the file in Chrome
- Share your screen
- Let THEM type in the form / interact with it
- The chatbot actually works (add your Anthropic API key to see it live)

**For the chatbot demo to work live:** Open `faq_chatbot/index.html`, find the fetch() call to the Anthropic API, and note it already uses your claude-sonnet model. The API key needs to be added — or better, host it through a simple backend so your key isn't exposed.

---

## The Sales Script (Condensed)

**Cold email goal:** Get a 15-minute call, not a sale.

**On the call:**
1. "What's the one admin task that eats most of your week?"
2. Listen. Don't talk yet.
3. Show the relevant demo LIVE.
4. "I can have this running for you in 7 days. Here's what it costs."
5. Send proposal same day.

**Pricing:**
- After-hours lead capture: **$900** + $150/month
- Appointment reminder system: **$1,200** + $200/month
- FAQ chatbot: **$1,000** + $200/month
- Bundle all 3: **$2,500** + $450/month (save $600)

**Always:** 50% upfront before you start. Non-negotiable.

---

## Realistic First 30 Days

Week 1: Send 20 cold emails. Goal: 3-5 replies.
Week 2: Get on 2-3 calls. Show demos. Send proposals.
Week 3: Close 1 deal. Start building.
Week 4: Deliver. Ask for testimonial + referral.

**At $1,000/project + $200/month retention:**
- 1 client = $1,000 now + $200/month recurring
- 5 clients = $5,000 now + $1,000/month recurring
- 10 clients = $10,000 now + $2,000/month recurring

The monthly retainers compound. That's the play.

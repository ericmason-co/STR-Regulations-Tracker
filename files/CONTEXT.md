# Global STR Regulation Tracker — Project Context

## Overview
Eric Mason's living database tracking short-term rental (STR) regulations across 240+ jurisdictions worldwide. Originally built December 2025. Published as a LinkedIn article and available at vrinsider.com/2p8fmhs2.

Community-sourced via the Vacation Rental Professionals Group (21K+ members on LinkedIn).

## Current State
- Built as a Word doc + Excel spreadsheet (Global_STR_Regulations_Comprehensive_Database.xlsx)
- 3 sheets: Executive Summary, US - Detailed by City, International - Overview
- Last data refresh: December 2025

## Data Schema — 21 Fields Per US Jurisdiction

| # | Field | Example Values |
|---|-------|---------------|
| 1 | State | California |
| 2 | City/Jurisdiction | San Francisco |
| 3 | Regulatory Status | Active / Restricted / Banned / Pending / None |
| 4 | License/Registration Required | Yes / No / Yes (DBPR) |
| 5 | Tax Registration Required | Yes / No |
| 6 | Fees | $450/yr, $100-$400, None |
| 7 | Primary Residence Required | Yes / No / Yes (home-share) |
| 8 | Annual Rental Day Cap | None, 90 days, 60 days |
| 9 | Occupancy Limit | Owner + 2 guests, 10 max |
| 10 | Tax Rate | 14% TOT, 6% state + 7% local |
| 11 | Zoning Restrictions | All zones, Commercial only, Resort zones |
| 12 | Minimum Stay Requirement | None, 30 days, 31+ days |
| 13 | Density/Spacing Rules | 150ft buffer, 3+ unit buildings prohibited |
| 14 | Insurance Required | Required / Varies / N/A |
| 15 | Platform Obligations | Yes / No / Platforms block unregistered |
| 16 | Compliance Notes | Registration + inspection, Annual renewal |
| 17 | Effective Date / Last Updated | Sept 2023, April 11 2025, Current |
| 18 | Key Notes | Summary of regulation |
| 19 | Penalties | Up to $10,000, $1,000/day, Fines apply |
| 20 | Additional Context | Enforcement notes, trends |
| 21 | Source | Rent Responsibly 2025, iGMS 2025, Awning 2025 |

## US Data Coverage

### California (13 cities)
- San Francisco, Los Angeles, San Diego, Oakland, Santa Monica, San Jose
- Palm Springs, Anaheim, South Lake Tahoe, Big Bear Lake, Joshua Tree
- State Level (SB 346 data-sharing law, Oct 2025)

### Florida (13+ markets)
- State (DBPR licensing req), Miami, Miami Beach, Orlando, Tampa, Clearwater
- St. Augustine, Palm Coast, Pinellas County, Cocoa Beach
- State preemption: SB 280 vetoed June 2024

### Texas (9 cities)
- Austin (major 2025 overhaul), Houston (first regulations 2025)
- San Antonio, Dallas, Fort Worth, El Paso, Lubbock, Amarillo, Alpine

### New York
- New York City (Local Law 18 — strictest in nation, Sept 2023)
  - Owner + 2 guests max, 1-2 family homes only, platforms block unregistered
- State Level (Multiple Dwelling Law)

### North Carolina
- State Level (2018 law prevents full bans, Vacation Rental Act)
- Asheville (Restricted — banned outside resort zones)

### Hawaii
- State Level (SB 2919 county authority, 2024)
- Honolulu/Oahu (Up to $10,000 fines, aggressive enforcement)
- Maui County (Phase-out programs, housing crisis driven)

### Colorado
- State Level (HB 25-1247 raises lodging tax cap to 6% with voter approval, April 11 2025)

### Arizona (State Preemption)
- Phoenix, Scottsdale (state preemption prevents bans; nuisance-based enforcement)

### Tennessee
- State Level (boom in Nashville, local permitting)

### Failed Legislation States
- Idaho: SB 1162 failed April 1 2025 (would have prevented local STR prohibitions, defeated 23-11)
- Kentucky: Failed bill
- Arkansas: Failed bill

### Additional States (all 50 covered)
- Mississippi, Louisiana (New Orleans French Quarter heavy regulation), Oklahoma
- Kansas, Nebraska, South Dakota, Montana, Oregon, South Carolina
- Maine, Vermont, Idaho (no broker license req), Pennsylvania (2025 ruling)
- All remaining states: State sales tax / local control baseline

## Key 2025 US Regulatory Trends
1. California SB 346: Platform data-sharing mandate (Oct 2025)
2. Austin TX: Major overhaul
3. Houston TX: First-ever STR regulations
4. HB 25-1247 (CO): Lodging tax cap raised to 6%
5. Palm Coast FL: Ordinance 2025-01, mandatory owner background checks
6. Pinellas County FL: Ordinance 2025-01, biennial safety inspections, staggered ZIP deadlines
7. St. Augustine FL: Resolution 2025-41 tiered zoning fee schedule

## International Coverage (70+ locations)

### Europe
- Barcelona: Complete STR phase-out by 2028
- Spain: €64M Airbnb fine for unlicensed listings; digital monitoring spreading to Florence, Rome
- EU: Data-sharing mandate (DAC7) affecting all platforms
- Portugal: Municipal control returns after national rollback; Lisbon micro-containment zones
- France (Paris, Nice, Lyon), Germany, Netherlands, Italy (Florence, Rome)
- Greece: Comprehensive safety standards (Oct 2025)
- UK

### Asia-Pacific
- Japan: Tokyo wards implement weekend-only restrictions; minpaku framework tightening
- Australia, New Zealand

### Americas
- Canada, Mexico, South America

## International Trends
- Housing-first policies driving restrictions (Barcelona model)
- Platform accountability: License verification, auto-delisting
- Digital monitoring systems (Spain → Florence, Rome)
- Hyperlocal variations: Neighborhood-level and ward-level rules
- EU DAC7 data-sharing framework spreading

## Broker License Requirements by State (Separate Research, Jan 2026)
States REQUIRING real estate broker license for STR management:
- Florida, California (exemption for transient <30 days hotel-like), New York, North Carolina
- Colorado (not required for hotel-like STR agreements), Arizona, Pennsylvania (2025 ruling: NOT required)

States NOT requiring broker license:
- Idaho, Maine, Vermont

Alternative licensing (property manager license vs broker):
- Montana, Oregon, South Carolina

## Project Goals / What This Is For
- Living document maintained by VRP Group community
- Intelligence resource for operators, investors, platforms, policymakers
- VRInsider content anchor (vrinsider.com)
- LinkedIn thought leadership for Eric Mason / VRP Group
- Community contribution via #STRRegulations hashtag

## Files
- Original XLSX: Global_STR_Regulations_Comprehensive_Database.xlsx
- LinkedIn article: https://www.linkedin.com/pulse/global-short-term-rental-regulations-tracker-eric-mason-uckpc
- Short URL: vrinsider.com/2p8fmhs2

## Potential Next Steps (Ideas for Claude Code session)
1. Rebuild as a proper web app / searchable database
2. Add update-tracking / changelog per jurisdiction
3. Build a crowdsourced submission form (Google Forms → Sheet pipeline)
4. Create an API endpoint for VRInsider to query live data
5. Auto-update via web scraping + AI summarization
6. Export to XLSX / PDF on demand
7. Add alert system for regulatory changes by market

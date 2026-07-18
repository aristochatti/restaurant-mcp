# Google Maps List Fetcher Scripts

This directory contains Python scripts for fetching places from Google Maps lists.

## Problem Statement

**Google Maps does NOT provide an official API for accessing user's saved places/lists.**

Shared list URLs (like `https://maps.app.goo.gl/...`) load content dynamically via JavaScript, making it impossible to extract place data with simple HTTP requests.

## Solutions Provided

### 1. `fetch_google_maps_list_final.py` (RECOMMENDED)

**Use this for:** Fetching places using place IDs with the Google Places API (New)

This is the **recommended approach** that:
- ✅ Uses your existing Google Maps API key (from resto-mcp)
- ✅ Requires minimal dependencies (only `requests`)
- ✅ Works with minimal user interaction after initial setup
- ✅ Is reliable and fast

#### How to Get Place IDs

**Method A: Using Browser DevTools (Recommended)**
1. Open your Google Maps list in Chrome
2. Press `F12` to open DevTools
3. Go to the **Console** tab
4. Run this JavaScript:
   ```javascript
   // Get all place IDs from the list
   Array.from(document.querySelectorAll('[data-place-id]')).map(el => el.getAttribute('data-place-id'))
   ```
5. Copy the output (array of place IDs)
6. Save to a text file (one ID per line)

**Method B: From Place URLs**
1. Open your list in Google Maps
2. Click on a place to view its details
3. Copy the URL - it will look like: `https://www.google.com/maps/place/NAME/place_id/...`
4. Extract the `place_id` from the URL (the part after `/place/` and before the next `/`)

**Method C: From Google Takeout**
1. Go to [Google Takeout](https://takeout.google.com/)
2. Select "Maps" > "Your Places"
3. Export as JSON
4. Use the `--takeout` option with the exported file

#### Usage

```bash
# Set your API key (same as your resto-mcp project)
export GOOGLE_MAPS_API_KEY=your_api_key_here

# Fetch places by IDs directly
python fetch_google_maps_list_final.py --place-ids ChIJN1t_tDeuEmsRUsoyG83frY4 ChIJIQBpAG2ahYAR_6128GcTUEo

# Or use a file with place IDs (one per line)
python fetch_google_maps_list_final.py --file my_places.txt

# Use Google Takeout export
python fetch_google_maps_list_final.py --takeout saved_places.json

# Save to custom output file
python fetch_google_maps_list_final.py --file my_places.txt --output my_restaurants.json
```

#### Output

The script will:
- Print places in a readable format with names, addresses, ratings, etc.
- Save to a JSON file (default: `places.json`)
- Include: name, address, rating, price level, opening hours, photos, location, types

### 2. `fetch_google_maps_list_playwright.py` (Alternative)

**Use this for:** Fully automated extraction from shared list URLs

This script uses **Playwright** to render JavaScript and extract place data automatically.

#### Requirements

```bash
pip install playwright
python -m playwright install
```

**Note:** Playwright requires browser installation and may not work in all environments (e.g., minimal Docker containers).

#### Usage

```bash
# Fetch from a shared list URL
python fetch_google_maps_list_playwright.py https://maps.app.goo.gl/your_list_id

# Run with visible browser (for debugging)
python fetch_google_maps_list_playwright.py --visible https://maps.app.goo.gl/your_list_id
```

#### Output

- Extracts places automatically from the shared list
- Saves to `google_maps_places.json`
- Includes: name, address, place ID, rating, URL

## Setup Instructions

### 1. Get a Google Maps API Key

You already have this configured for your `resto-mcp` project. Use the same key.

If you need a new one:
1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a new API key (or use existing)
3. Enable **Places API (New)**
4. Set the `GOOGLE_MAPS_API_KEY` environment variable

```bash
export GOOGLE_MAPS_API_KEY=your_key_here
```

### 2. Extract Place IDs (for Approach 1)

See the instructions above for `fetch_google_maps_list_final.py`.

### 3. Run the Script

```bash
# For the recommended approach
export GOOGLE_MAPS_API_KEY=your_key
python fetch_google_maps_list_final.py --file my_place_ids.txt
```

## Example Workflow

### For Your Restaurant List

1. **Extract place IDs from your list:**
   ```bash
   # Create a file with your place IDs
   echo "ChIJN1t_tDeuEmsRUsoyG83frY4" > my_restaurants.txt
   echo "ChIJIQBpAG2ahYAR_6128GcTUEo" >> my_restaurants.txt
   # Add more place IDs...
   ```

2. **Fetch details:**
   ```bash
   export GOOGLE_MAPS_API_KEY=your_key
   python fetch_google_maps_list_final.py --file my_restaurants.txt --output my_restaurants.json
   ```

3. **Use the data:**
   ```python
   import json
   with open('my_restaurants.json') as f:
       restaurants = json.load(f)
   for r in restaurants:
       print(f"{r['name']} - {r['address']} - Rating: {r.get('rating', 'N/A')}")
   ```

## Integration with resto-mcp

You can integrate the fetched places with your existing `resto-mcp` project:

```javascript
// In your server.js or places.js
import { readFileSync } from 'fs';

// Load pre-fetched places
const myPlaces = JSON.parse(readFileSync('./scripts/my_restaurants.json'));

// Use them as a fallback or for specific features
```

## Comparison of Approaches

| Approach | Dependencies | User Interaction | Reliability | Speed | Notes |
|----------|--------------|-------------------|-------------|-------|-------|
| **Place IDs + API** | `requests` | One-time ID extraction | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Uses existing API key |
| **Playwright** | `playwright` + browser | None | ⭐⭐⭐⭐ | ⭐⭐⭐ | Fully automated |
| **Google Takeout** | None | Manual export | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Not real-time |

## Limitations

1. **No Official API**: Google does not provide an official API for saved lists
2. **Manual Extraction**: For the recommended approach, you need to manually extract place IDs once
3. **Rate Limits**: The Places API has rate limits (check your Google Cloud quota)
4. **Authentication**: Shared lists may require authentication to view

## Troubleshooting

### "API key not valid"
- Make sure you've enabled **Places API (New)** in Google Cloud Console
- Check that your API key is correct
- Verify you have billing enabled (required for Places API)

### "Place not found"
- Verify the place ID is correct
- Some places may not be accessible via the API
- Check if the place still exists

### "403 Forbidden"
- Your API key may have IP restrictions
- Check restrictions in Google Cloud Console
- Try without restrictions for testing

### "ModuleNotFoundError: No module named 'requests'"
```bash
pip install requests
```

### "ModuleNotFoundError: No module named 'playwright'"
```bash
pip install playwright
python -m playwright install
```

## Alternative: Google Takeout

If you want all your saved places (not just from one list):

1. Go to [Google Takeout](https://takeout.google.com/)
2. Deselect all
3. Select "Maps" > "Your Places"
4. Choose JSON format
5. Export and download
6. Use with: `python fetch_google_maps_list_final.py --takeout Saved\)Places.json`

This gives you all your saved places in GeoJSON format, but it's a manual process.

## Contributing

If you find a better way to extract places from Google Maps lists, please contribute!

The ideal solution would:
- ✅ Require no manual steps
- ✅ Use only official APIs
- ✅ Work with minimal dependencies
- ✅ Be reliable and fast

Currently, no such solution exists due to Google's API limitations.

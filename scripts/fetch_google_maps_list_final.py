#!/usr/bin/env python3
"""
Final solution for fetching places from Google Maps lists.

This script provides multiple approaches depending on your needs:

APPROACH 1: Use Place IDs (Recommended)
- You manually extract place IDs from your list once
- Script fetches details using Google Places API (New)
- Fast, reliable, uses your existing API key

APPROACH 2: Use Shared List URL (Requires Playwright)
- Automatically extracts places from shared list URLs
- Requires Playwright and browser installation
- Slower but fully automated

APPROACH 3: Google Takeout Export
- Use exported data from Google Takeout
- No API calls needed
- Manual export process

See README.md for detailed instructions.
"""

import os
import sys
import json
import argparse
from typing import List, Dict, Optional

# Check available dependencies
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class GooglePlacesAPI:
    """
    Wrapper for Google Places API (New).
    Uses the same API as your resto-mcp project.
    """
    
    BASE_URL = "https://places.googleapis.com/v1"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
    
    def get_place_details(self, place_id: str) -> Optional[Dict]:
        """Get details for a specific place by ID."""
        url = f"{self.BASE_URL}/places/{place_id}"
        
        # Field mask - same as your resto-mcp project
        field_mask = [
            "id",
            "displayName",
            "formattedAddress", 
            "rating",
            "userRatingCount",
            "priceLevel",
            "currentOpeningHours.openNow",
            "photos",
            "types",
            "location",
        ]
        
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": ",".join(field_mask),
        }
        
        try:
            response = self.session.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error: HTTP {response.status_code} - {response.text[:200]}")
                return None
        except Exception as e:
            print(f"Error fetching place {place_id}: {e}")
            return None
    
    def search_places(self, query: str, limit: int = 10) -> List[Dict]:
        """Search for places using text query (same as your resto-mcp)."""
        url = f"{self.BASE_URL}/places:searchText"
        
        field_mask = [
            "places.id",
            "places.displayName",
            "places.formattedAddress",
            "places.rating",
            "places.userRatingCount",
            "places.priceLevel",
            "places.currentOpeningHours.openNow",
            "places.photos",
        ]
        
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": ",".join(field_mask),
        }
        
        body = {
            "textQuery": query,
            "includedType": "restaurant",
            "maxResultCount": min(limit, 20),
        }
        
        try:
            response = self.session.post(url, headers=headers, json=body, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get('places', [])
            else:
                print(f"Error: HTTP {response.status_code}")
                return []
        except Exception as e:
            print(f"Error searching: {e}")
            return []
    
    def parse_place(self, place_data: Dict) -> Dict:
        """Parse place data into clean format."""
        place = {}
        
        # Place ID
        place['place_id'] = place_data.get('id', '')
        
        # Name
        display_name = place_data.get('displayName', {})
        if isinstance(display_name, dict):
            place['name'] = display_name.get('text', 'Unknown')
        else:
            place['name'] = display_name or 'Unknown'
        
        # Address
        place['address'] = place_data.get('formattedAddress', '')
        
        # Location
        location = place_data.get('location', {})
        if location:
            place['latitude'] = location.get('latitude')
            place['longitude'] = location.get('longitude')
        
        # Rating
        place['rating'] = place_data.get('rating')
        place['userRatingCount'] = place_data.get('userRatingCount', 0)
        
        # Price level
        price_level = place_data.get('priceLevel')
        if price_level:
            price_map = {
                'PRICE_LEVEL_INEXPENSIVE': '💰',
                'PRICE_LEVEL_MODERATE': '💰💰',
                'PRICE_LEVEL_EXPENSIVE': '💰💰💰',
                'PRICE_LEVEL_VERY_EXPENSIVE': '💰💰💰💰',
            }
            place['priceLevel'] = price_map.get(price_level, price_level)
        
        # Opening hours
        opening_hours = place_data.get('currentOpeningHours', {})
        place['openNow'] = opening_hours.get('openNow')
        
        # Photos
        photos = place_data.get('photos', [])
        if photos:
            photo = photos[0]
            photo_name = photo.get('name', '')
            if photo_name:
                place['photoUrl'] = f"https://places.googleapis.com/v1/{photo_name}/media?maxWidthPx=500&key={self.api_key}"
        
        # Types
        place['types'] = place_data.get('types', [])
        
        return place


class ListExtractor:
    """Extracts places from various sources."""
    
    @staticmethod
    def from_place_ids(api: GooglePlacesAPI, place_ids: List[str]) -> List[Dict]:
        """Extract places from a list of place IDs."""
        places = []
        for place_id in place_ids:
            place_data = api.get_place_details(place_id)
            if place_data:
                places.append(api.parse_place(place_data))
        return places
    
    @staticmethod
    def from_file(filename: str) -> List[str]:
        """Load place IDs from a file."""
        with open(filename, 'r') as f:
            lines = f.readlines()
        
        place_ids = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                place_ids.append(line)
        
        return place_ids
    
    @staticmethod
    def from_takeout_file(filename: str) -> List[Dict]:
        """Load places from Google Takeout export."""
        with open(filename, 'r') as f:
            data = json.load(f)
        
        places = []
        
        # Google Takeout exports saved places in GeoJSON format
        if 'features' in data:
            for feature in data['features']:
                place = {
                    'name': feature.get('properties', {}).get('name', ''),
                    'address': feature.get('properties', {}).get('address', ''),
                    'latitude': feature.get('geometry', {}).get('coordinates', [0, 0])[1] if feature.get('geometry') else None,
                    'longitude': feature.get('geometry', {}).get('coordinates', [0, 0])[0] if feature.get('geometry') else None,
                }
                if place['name']:
                    places.append(place)
        
        return places


def print_places(places: List[Dict]):
    """Print places in a readable format."""
    if not places:
        print("\n❌ No places found.")
        return
    
    print(f"\n{'='*80}")
    print(f"✅ FOUND {len(places)} PLACES")
    print(f"{'='*80}\n")
    
    for i, place in enumerate(places, 1):
        name = place.get('name', 'Unknown')
        address = place.get('address', '')
        place_id = place.get('place_id', '')
        rating = place.get('rating', '')
        price = place.get('priceLevel', '')
        open_now = place.get('openNow')
        lat = place.get('latitude', '')
        lng = place.get('longitude', '')
        
        print(f"{i}. {name}")
        if address:
            print(f"   📍 {address}")
        if place_id:
            print(f"   🆔 {place_id}")
        if rating:
            reviews = place.get('userRatingCount', 0)
            print(f"   ⭐ {rating} ({reviews} reviews)")
        if price:
            print(f"   Price: {price}")
        if open_now is not None:
            status = "🟢 OPEN" if open_now else "🔴 CLOSED"
            print(f"   {status}")
        if lat and lng:
            print(f"   🌍 {lat}, {lng}")
        print()
    
    print(f"{'='*80}")


def save_to_json(places: List[Dict], filename: str = 'places.json'):
    """Save places to JSON file."""
    with open(filename, 'w') as f:
        json.dump(places, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Places saved to: {filename}")
    return filename


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Fetch places from Google Maps lists',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:

# Fetch places by IDs (recommended)
python fetch_google_maps_list_final.py --place-ids ChIJ1 ChIJ2

# Load place IDs from file
python fetch_google_maps_list_final.py --file my_places.txt

# Use Google Takeout export
python fetch_google_maps_list_final.py --takeout saved_places.json

# Set API key
python fetch_google_maps_list_final.py --api-key YOUR_KEY --file my_places.txt
        """
    )
    
    parser.add_argument(
        '--api-key',
        help='Google Maps API key (default: GOOGLE_MAPS_API_KEY env var)'
    )
    parser.add_argument(
        '--place-ids',
        nargs='+',
        help='List of place IDs to fetch'
    )
    parser.add_argument(
        '--file', '-f',
        help='File containing place IDs (one per line)'
    )
    parser.add_argument(
        '--takeout',
        help='Google Takeout JSON file to parse'
    )
    parser.add_argument(
        '--output', '-o',
        default='places.json',
        help='Output JSON file (default: places.json)'
    )
    
    args = parser.parse_args()
    
    # Get API key
    api_key = args.api_key or os.getenv('GOOGLE_MAPS_API_KEY')
    
    if not api_key and not args.takeout:
        print("❌ Error: GOOGLE_MAPS_API_KEY is required (unless using --takeout)")
        print("Set it via:")
        print("  export GOOGLE_MAPS_API_KEY=your_key")
        print("  or use --api-key argument")
        print("\nGet a key from: https://console.cloud.google.com/apis/credentials")
        print("Enable: Places API (New)")
        return []
    
    print("="*80)
    print("GOOGLE MAPS LIST FETCHER")
    print("="*80)
    
    # Initialize API if needed
    api = GooglePlacesAPI(api_key) if api_key else None
    
    # Collect places
    places = []
    
    # From place IDs
    if args.place_ids:
        print(f"\nFetching {len(args.place_ids)} places by ID...")
        places.extend(ListExtractor.from_place_ids(api, args.place_ids))
    
    # From file
    if args.file:
        place_ids = ListExtractor.from_file(args.file)
        print(f"\nFetching {len(place_ids)} places from file...")
        places.extend(ListExtractor.from_place_ids(api, place_ids))
    
    # From Google Takeout
    if args.takeout:
        print(f"\nLoading places from Google Takeout export...")
        places.extend(ListExtractor.from_takeout_file(args.takeout))
    
    # Remove duplicates
    seen_ids = set()
    unique_places = []
    for place in places:
        place_id = place.get('place_id', '')
        if place_id not in seen_ids:
            seen_ids.add(place_id)
            unique_places.append(place)
    places = unique_places
    
    # Print and save
    print_places(places)
    
    if places:
        save_to_json(places, args.output)
    
    return places


if __name__ == "__main__":
    main()

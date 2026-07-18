#!/usr/bin/env python3
"""
Script to fetch places from a shared Google Maps list using Playwright.
This can render JavaScript and extract the place data.
"""

import asyncio
import json
import re
import sys
from typing import List, Dict, Optional
from pathlib import Path

# Check if playwright is available
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class GoogleMapsListFetcher:
    """Fetcher for Google Maps shared lists using Playwright."""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.timeout = 30000  # 30 seconds
    
    async def fetch_list_places(self, url: str) -> List[Dict]:
        """Fetch places from a shared Google Maps list URL."""
        if not PLAYWRIGHT_AVAILABLE:
            print("Error: Playwright is not installed.")
            print("Install it with: pip install playwright && python -m playwright install")
            return []
        
        print(f"Fetching from: {url}")
        
        places = []
        
        async with async_playwright() as p:
            # Launch browser
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            try:
                # Navigate to the URL
                await page.goto(url, timeout=self.timeout)
                print("Page loaded successfully")
                
                # Wait for the list to load
                # Google Maps lists load dynamically, so we need to wait
                await page.wait_for_selector('div[role="main"]', timeout=self.timeout)
                print("Main content loaded")
                
                # Try to find place entries
                # Google Maps list items typically have specific attributes
                
                # Method 1: Look for elements with data-place-id attribute
                place_elements = await page.query_selector_all('[data-place-id]')
                if place_elements:
                    print(f"Found {len(place_elements)} place elements with data-place-id")
                    for element in place_elements:
                        place = await self.extract_place_from_element(element, page)
                        if place:
                            places.append(place)
                
                # Method 2: If no data-place-id, try to find place cards
                if not places:
                    print("Trying alternative selector...")
                    # Look for elements that look like place cards
                    place_cards = await page.query_selector_all('div[role="article"], div[data-item-id]')
                    if place_cards:
                        print(f"Found {len(place_cards)} place card elements")
                        for card in place_cards:
                            place = await self.extract_place_from_card(card, page)
                            if place:
                                places.append(place)
                
                # Method 3: Extract from the page content as JSON
                if not places:
                    print("Trying JSON extraction from page...")
                    places = await self.extract_places_from_page_content(page)
                
                # Method 4: Last resort - extract text content
                if not places:
                    print("Trying text extraction...")
                    places = await self.extract_places_from_text(page)
                
                print(f"Total places found: {len(places)}")
                
            except Exception as e:
                print(f"Error during page loading: {e}")
            
            finally:
                await browser.close()
        
        return places
    
    async def extract_place_from_element(self, element, page) -> Optional[Dict]:
        """Extract place data from an element with data-place-id."""
        try:
            place_id = await element.get_attribute('data-place-id')
            
            # Get name
            name_element = await element.query_selector('div[role="heading"], h1, h2, h3, .title')
            name = await name_element.inner_text() if name_element else ''
            
            # Get address
            address_element = await element.query_selector('.address, .subtitle, [data-item-prop="address"]')
            address = await address_element.inner_text() if address_element else ''
            
            # Get rating
            rating_element = await element.query_selector('[aria-label*="stars"], .rating')
            rating = await rating_element.get_attribute('aria-label') if rating_element else ''
            
            # Get URL
            link_element = await element.query_selector('a[href*="maps/place/"]')
            url = await link_element.get_attribute('href') if link_element else ''
            
            if name or place_id:
                return {
                    'place_id': place_id,
                    'name': name.strip(),
                    'address': address.strip(),
                    'rating': rating,
                    'url': url,
                }
        except Exception as e:
            print(f"Error extracting place: {e}")
        
        return None
    
    async def extract_place_from_card(self, card, page) -> Optional[Dict]:
        """Extract place data from a place card element."""
        try:
            # Get name
            name_element = await card.query_selector('div[role="heading"], h1, h2, h3')
            name = await name_element.inner_text() if name_element else ''
            
            # Get address
            address_element = await card.query_selector('.address, .subtitle')
            address = await address_element.inner_text() if address_element else ''
            
            # Get place ID from URL
            link_element = await card.query_selector('a[href*="place/"]')
            if link_element:
                url = await link_element.get_attribute('href')
                # Extract place ID from URL
                place_id_match = re.search(r'/place/([^/]+)', url)
                place_id = place_id_match.group(1) if place_id_match else ''
            else:
                place_id = ''
                url = ''
            
            if name:
                return {
                    'place_id': place_id,
                    'name': name.strip(),
                    'address': address.strip(),
                    'url': url,
                }
        except Exception as e:
            print(f"Error extracting from card: {e}")
        
        return None
    
    async def extract_places_from_page_content(self, page) -> List[Dict]:
        """Extract places by looking for JSON data in the page."""
        places = []
        
        try:
            # Get all script content
            scripts = await page.query_selector_all('script')
            
            for script in scripts:
                content = await script.inner_text()
                
                # Look for JSON data
                if 'window.' in content or 'var ' in content:
                    # Try to find JSON in variable assignments
                    json_matches = re.findall(r'=\s*({.*?})\s*;', content, re.DOTALL)
                    for json_str in json_matches:
                        try:
                            data = json.loads(json_str)
                            places.extend(self.parse_places_from_json(data))
                        except:
                            continue
        except Exception as e:
            print(f"Error extracting from page content: {e}")
        
        return places
    
    async def extract_places_from_text(self, page) -> List[Dict]:
        """Extract places from text content as a last resort."""
        places = []
        
        try:
            # Get all text content
            text = await page.evaluate('() => document.body.innerText')
            
            # Split by lines and look for place-like entries
            lines = text.split('\n')
            
            # Look for lines that look like place names (capitalized, reasonable length)
            for line in lines:
                line = line.strip()
                if len(line) > 3 and len(line) < 100 and line[0].isupper():
                    # This might be a place name
                    places.append({'name': line})
            
            # Limit to reasonable number
            if len(places) > 50:
                places = places[:50]
        except Exception as e:
            print(f"Error extracting from text: {e}")
        
        return places
    
    def parse_places_from_json(self, data: Dict) -> List[Dict]:
        """Parse places from JSON data."""
        places = []
        
        def search(obj):
            if isinstance(obj, dict):
                # Check if this looks like a place
                if any(k in obj for k in ['placeId', 'place_id', 'name', 'title', 'formattedAddress']):
                    place = {}
                    place['place_id'] = obj.get('placeId') or obj.get('place_id') or ''
                    place['name'] = obj.get('name') or obj.get('title') or ''
                    place['address'] = obj.get('formattedAddress') or obj.get('address') or ''
                    place['rating'] = obj.get('rating')
                    place['types'] = obj.get('types', [])
                    
                    if place.get('name'):
                        places.append(place)
                
                # Search nested
                for v in obj.values():
                    search(v)
            
            elif isinstance(obj, list):
                for item in obj:
                    search(item)
        
        search(data)
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
        url = place.get('url', '')
        
        print(f"{i}. {name}")
        if address:
            print(f"   📍 {address}")
        if place_id:
            print(f"   🆔 {place_id}")
        if rating:
            print(f"   ⭐ {rating}")
        if url:
            print(f"   🔗 {url}")
        print()
    
    print(f"{'='*80}")


def save_to_json(places: List[Dict], filename: str = 'google_maps_places.json'):
    """Save places to JSON file."""
    with open(filename, 'w') as f:
        json.dump(places, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Places saved to: {filename}")
    return filename


def main():
    """Main entry point."""
    list_url = "https://maps.app.goo.gl/tt8pBjex973wSz8z6"
    headless = True
    
    if len(sys.argv) > 1:
        list_url = sys.argv[1]
    
    if '--visible' in sys.argv or '-v' in sys.argv:
        headless = False
    
    print("="*80)
    print("GOOGLE MAPS LIST FETCHER (Playwright)")
    print("="*80)
    
    if not PLAYWRIGHT_AVAILABLE:
        print("\n❌ Playwright is not installed.")
        print("Install it with:")
        print("  pip install playwright")
        print("  python -m playwright install")
        return []
    
    fetcher = GoogleMapsListFetcher(headless=headless)
    
    # Run the async fetcher
    places = asyncio.run(fetcher.fetch_list_places(list_url))
    
    print_places(places)
    
    if places:
        save_to_json(places)
    
    return places


if __name__ == "__main__":
    main()

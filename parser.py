"""Парсер объявлений с Krisha.kz"""
import requests
import re
import json
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin

from config import KRISHA_SEARCH_URL, HEADERS

def parse_listings(params: dict = None) -> list:
    listings = []
    url = KRISHA_SEARCH_URL
    
    if params:
        query_parts = []
        if params.get("rooms"):
            query_parts.append(f"das[live.rooms]={params['rooms']}")
        if params.get("price_from"):
            query_parts.append(f"das[price][from]={params['price_from']}")
        if params.get("price_to"):
            query_parts.append(f"das[price][to]={params['price_to']}")
        if params.get("area_from"):
            query_parts.append(f"das[live.square][from]={params['area_from']}")
        if params.get("area_to"):
            query_parts.append(f"das[live.square][to]={params['area_to']}")
        if query_parts:
            url += "?" + "&".join(query_parts)
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        scripts = soup.find_all("script")
        for script in scripts:
            if script.string and "window.__INITIAL_STATE__" in script.string:
                match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', script.string, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        if "catalog" in data and "items" in data["catalog"]:
                            for item in data["catalog"]["items"]:
                                listing = extract_listing_data(item)
                                if listing:
                                    listings.append(listing)
                        break
                    except json.JSONDecodeError:
                        pass
        
        if not listings:
            listings = parse_html_listings(soup)
            
    except Exception as e:
        print(f"Ошибка парсинга: {e}")
    
    return listings

def extract_listing_data(item: dict) -> dict:
    try:
        return {
            "id": str(item.get("id", "")),
            "title": item.get("title", ""),
            "price": item.get("price", 0),
            "rooms": item.get("rooms", 0),
            "area": item.get("square", 0.0),
            "floor": f"{item.get('floor', '')}/{item.get('floors', '')}",
            "address": item.get("address", ""),
            "district": item.get("district", ""),
            "url": f"https://krisha.kz/a/show/{item.get('id', '')}",
            "photo_url": item.get("photo", ""),
            "description": item.get("description", ""),
            "published_at": item.get("created_at", datetime.now().isoformat())
        }
    except Exception:
        return None

def parse_html_listings(soup: BeautifulSoup) -> list:
    listings = []
    cards = soup.find_all("div", class_="a-card__inc")
    
    for card in cards:
        try:
            link_tag = card.find("a", class_="a-card__title")
            if not link_tag:
                continue
            
            url = urljoin("https://krisha.kz", link_tag.get("href", ""))
            listing_id_match = re.search(r'/a/show/(\d+)', url)
            listing_id = listing_id_match.group(1) if listing_id_match else ""
            
            title = link_tag.get_text(strip=True)
            
            price_tag = card.find("div", class_="a-card__price")
            price_text = price_tag.get_text(strip=True) if price_tag else "0"
            price_digits = re.sub(r'[^\d]', '', price_text)
            price = int(price_digits) if price_digits else 0
            
            desc_tag = card.find("div", class_="a-card__text")
            desc = desc_tag.get_text(strip=True) if desc_tag else ""
            
            rooms_match = re.search(r'(\d+)-комн', desc)
            rooms = int(rooms_match.group(1)) if rooms_match else 0
            
            area_match = re.search(r'(\d+(?:\.\d+)?)\s*м²', desc)
            area = float(area_match.group(1)) if area_match else 0.0
            
            floor_match = re.search(r'(\d+)/(\d+)', desc)
            floor = f"{floor_match.group(1)}/{floor_match.group(2)}" if floor_match else ""
            
            address_tag = card.find("div", class_="a-card__subtitle")
            address = address_tag.get_text(strip=True) if address_tag else ""
            
            photo_tag = card.find("img", class_="a-card__image")
            photo_url = photo_tag.get("src", "") if photo_tag else ""
            
            listings.append({
                "id": listing_id,
                "title": title,
                "price": price,
                "rooms": rooms,
                "area": area,
                "floor": floor,
                "address": address,
                "district": "",
                "url": url,
                "photo_url": photo_url,
                "description": desc,
                "published_at": datetime.now().isoformat()
            })
            
        except Exception as e:
            print(f"Ошибка парсинга карточки: {e}")
            continue
    
    return listings

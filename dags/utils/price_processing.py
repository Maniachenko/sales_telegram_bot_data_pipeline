import re


# Helper function to parse price strings into floats
def parse_price(price_str):
    # Remove non-numeric characters except for decimal points or commas
    clean_str = re.sub(r'[^0-9.,]', '', price_str)
    clean_str = clean_str.replace(',', '.').replace("'", '.')

    try:
        # If it contains a decimal, treat it as a float
        if '.' in clean_str:
            return float(clean_str)
        # Otherwise, treat the last two digits as the decimal part
        elif len(clean_str) > 2:
            return float(clean_str[:-2] + '.' + clean_str[-2:])
        else:
            return float(clean_str)
    except ValueError:
        return None


# EsoMarket Condition
def process_esomarket(price_str):
    price = parse_price(price_str)
    return price if price else None


def process_penny(price_str, price_type):
    # Extract all numeric parts from the price string
    prices = re.findall(r'\d+[.,]?\d*', price_str)

    # Clean up extracted prices and convert them to floats
    parsed_prices = [parse_price(p) for p in prices if parse_price(p) is not None]

    # Common cents values like 90 or 99
    common_cents = [90, 99]

    # Handle cases based on the length of parsed prices
    if len(parsed_prices) == 3:
        # Handle cases like "19 90 25.90 2"
        item_price = float(f"{int(parsed_prices[0])}.{int(parsed_prices[1])}")
        initial_price = parsed_prices[2]
        return {"item_price": item_price, "initial_price": initial_price}

    if len(parsed_prices) == 2:
        # If the second price is commonly a "cents" part like 90 or 99, merge with the first
        if parsed_prices[1] in common_cents:
            return {"item_price": float(f"{int(parsed_prices[0])}.{int(parsed_prices[1])}")}
        else:
            return {"item_price": parsed_prices[0], "initial_price": parsed_prices[1]}

    if len(parsed_prices) == 1:
        return {"item_price": parsed_prices[0]}

    return None


# Billa Condition
def process_billa(price_str, price_type):
    # Detect volume keywords: pri koupi, kupte, etc.
    volume_keywords = ['pri', 'koupi', 'kupte', 'ks', 'bodi', 'bodu', 'up te', 'aza']
    volume_detected = any(keyword in price_str.lower() for keyword in volume_keywords)

    # Extract numeric parts from the string
    prices = re.findall(r'\d+[.,]?\d*', price_str)
    parsed_prices = [parse_price(p) for p in prices if parse_price(p) is not None]

    # Handle specific distracted membership or volume words
    if 'bodi' in price_str.lower() or 'bodu' in price_str.lower():
        return {'item_member_price': '75bodi'}

    # Check if there are two prices and handle them
    if len(parsed_prices) == 2:
        # If the second value is an integer <5, treat it as volume, not initial_price
        if parsed_prices[1] < 5 and parsed_prices[1].is_integer():
            return {"item_price": parsed_prices[0], "volume": str(int(parsed_prices[1]))}
        else:
            return {"item_price": parsed_prices[0], "initial_price": parsed_prices[1]}
    elif len(parsed_prices) == 1:
        return {"item_price": parsed_prices[0]}

    return None


# Define Albert Hypermarket parsing method
def process_albert_hypermarket(price_str, price_type):
    # Clean string by keeping numbers and relevant separators
    clean_str = re.sub(r'[^0-9\s.,\'\-:]', '', price_str)  # Allow special chars like -, :, '

    # Handle specific cases for '-' or ':' as separators for integer prices
    combined_prices = []
    tokens = clean_str.split()

    for token in tokens:
        # Case 1: Numbers ending with "-" or ":"
        if token.endswith('-') or token.endswith(':'):
            token = token[:-1]  # Remove the trailing symbol
            combined_prices.append(parse_price(token))
        elif "'" in token:
            # Case 2: Handle cases like "31'90"
            parts = token.split("'")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                combined_price = f"{parts[0]}.{parts[1]}"
                combined_prices.append(parse_price(combined_price))
            else:
                combined_prices.append(parse_price(token))
        else:
            combined_prices.append(parse_price(token))

    # Filter out None values
    parsed_prices = [p for p in combined_prices if p is not None]

    # Condition: If the price is less than 5, treat it as invalid (exclude it)
    if parsed_prices and parsed_prices[0] < 5:
        return None

    # Assign prices based on the price_type
    if price_type == "item_member_price":
        if parsed_prices:
            return {"item_member_price": parsed_prices[0]}
    elif price_type == "item_initial_price":
        if parsed_prices:
            return {"item_initial_price": parsed_prices[0]}
    else:
        if parsed_prices:
            return {"item_price": parsed_prices[0]}

    return None


# Function to handle Tesco Supermarket OCR strings
def process_tesco_supermarket(price_str, price_type):
    # Handle dates (e.g., "12.7. - 14.7.") by ignoring them
    date_pattern = r'\d{1,2}\.\d{1,2}\.\s*-\s*\d{1,2}\.\d{1,2}\.'  # Pattern for dates like "12.7. - 14.7."
    clean_str = re.sub(date_pattern, '', price_str)

    # Skip strings with percentages or irrelevant text
    if "%" in clean_str or "HOP" in clean_str:
        return None

    # Extract price values, specifically for club card or "cena" keyword
    prices = re.findall(r'\d+[.,]?\d*', clean_str)
    parsed_prices = [parse_price(p) for p in prices if parse_price(p) is not None]

    # Logic to differentiate between item prices and initial prices
    if price_type == "item_member_price":
        if parsed_prices:
            return {"item_member_price": parsed_prices[0]}
    elif price_type == "item_initial_price":
        if parsed_prices:
            return {"item_initial_price": parsed_prices[0]}
    else:
        if parsed_prices:
            return {"item_price": parsed_prices[0]}

    return None


# Lidl Condition
def process_lidl(price_str):
    return parse_price(price_str)


# Kaufland Condition
def process_kaufland(price_str, price_type):
    if re.search(r'(\d+[.,]\d+)\s+(\d+[.,]\d+)', price_str):
        return None  # Skip sequences of more than 2 prices

    prices = re.findall(r'\d+[.,]?\d*', price_str)
    parsed_prices = [parse_price(p) for p in prices if parse_price(p) is not None]

    if len(parsed_prices) == 2:
        return {"item_price": parsed_prices[-1], "initial_price": parsed_prices[0]}
    elif len(parsed_prices) == 1:
        return {"item_price": parsed_prices[0]}
    return None


# Flop Top Condition
def process_flop_top(price_str, price_type):
    prices = re.findall(r'\d+[.,]?\d*', price_str)
    parsed_prices = [parse_price(p) for p in prices if parse_price(p) is not None]

    if len(parsed_prices) == 2:
        return {"item_price": parsed_prices[0], "initial_price": parsed_prices[1]}
    elif len(parsed_prices) == 1:
        return {"item_price": parsed_prices[0]}
    return None


# Travel Free Condition
def process_travel_free(price_str, price_type):
    # Removing any € symbols to focus only on numeric data
    clean_str = price_str.replace("€", "").strip()

    # Find all the price values in the string
    prices = re.findall(r'\d+[.,]?\d*', clean_str)
    parsed_prices = [parse_price(p) for p in prices if parse_price(p) is not None]

    # Ensure prices are sorted correctly (sale price is less than initial price)
    if len(parsed_prices) == 2:
        sale_price = min(parsed_prices)
        initial_price = max(parsed_prices)
        return {"item_price": sale_price, "initial_price": initial_price}

    # If we only have one price, return it as the item price
    elif len(parsed_prices) == 1:
        return {"item_price": parsed_prices[0]}

    return None


# CBA Potraviny Condition
def process_cba_potraviny(price_str):
    return parse_price(price_str)


# Bene Condition
def process_bene(price_str):
    return parse_price(price_str)


# CBA Premium Condition
def process_cba_premium(price_str):
    return parse_price(price_str)


# Lidl Shop Condition
def process_lidl_shop(price_str):
    return parse_price(price_str)


# CBA Market Condition
def process_cba_market(price_str):
    return parse_price(price_str)


# Updated Makro Condition with improved packaging detection
def process_makro(price_str, price_type):
    # Extract packaging information (must be at the beginning of the string)
    packaging_pattern = re.match(r'^(\d+-?\d?\s*(BAL|ks|A VICE|AViCE))', price_str)

    # If packaging is found, extract it and continue processing the price
    packaging = None
    if packaging_pattern:
        packaging = packaging_pattern.group()  # Extract the packaging
        price_str = price_str[len(packaging):].strip()  # Remove packaging from the price string

    # Extract all numeric parts (prices) after the packaging
    prices = re.findall(r'\d+[.,]?\d*', price_str)

    # Convert extracted prices to float
    parsed_prices = [parse_price(p) for p in prices if parse_price(p) is not None]

    # If there are two prices, assign them as item_price and initial_price
    if len(parsed_prices) >= 2:
        return {
            "item_price": parsed_prices[0],
            "initial_price": parsed_prices[1],
            "packaging": packaging
        }
    elif len(parsed_prices) == 1:
        # If there's only one price, treat it as the item price
        return {
            "item_price": parsed_prices[0],
            "packaging": packaging
        }
    else:
        return None


# Function to process Ratio price strings
def process_ratio(price_str):
    # Extract prices ignoring "bezDPH" or "vcetneDPH" text
    prices = re.findall(r'\d+[.,]?\d*', price_str)
    parsed_prices = [parse_price(p) for p in prices if parse_price(p) is not None]

    # If two prices are found, one should be item_price, the other initial_price
    if len(parsed_prices) == 2:
        return {"cena bez dph": parsed_prices[0], "item_price": parsed_prices[1]}
    return None


# Function to process Globus price strings
def process_globus(price_str, price_type):
    # Skip percentage strings or invalid non-numeric inputs
    if "%" in price_str or re.search(r'[^\d.,\'\s-]', price_str):
        return None

    # Handle cases like "14'90" or "44'90" by replacing apostrophe with a decimal point
    price_str = price_str.replace("'", ".")

    # Handle cases like "17 90" by joining them into a valid decimal format
    if re.search(r'\d+\s+\d{2}', price_str):
        price_str = price_str.replace(" ", ".")

    # Extract all numeric parts from the price string
    prices = re.findall(r'\d+[.,]?\d*', price_str)
    parsed_prices = [parse_price(p) for p in prices if parse_price(p) is not None]

    # Handle item_price and item_member_price based on price_type
    if price_type == "item_price":
        # If one price is found, return it as the item price
        if len(parsed_prices) == 1:
            return {"item_price": parsed_prices[0]}
    elif price_type == "item_member_price":
        # If member price is found, return it
        if len(parsed_prices) == 1:
            return {"item_member_price": parsed_prices[0]}

    return None


# Function to process Tamda Foods price strings
def process_tamda_foods(price_str, price_type):
    # Skip percentage strings and invalid inputs
    if "%" in price_str or "(" in price_str:
        return None

    # Handle cases like "1290 KC", "3490Kc", and "5290KC" (ignoring the "KC" part)
    price_str = re.sub(r'[KCkc]+', '', price_str).strip()

    # Extract numeric parts
    prices = re.findall(r'\d+[.,]?\d*', price_str)
    parsed_prices = [parse_price(p) for p in prices if parse_price(p) is not None]

    if len(parsed_prices) == 1:
        if price_type == "item_member_price":
            return {"item_member_price": parsed_prices[0]}
        elif price_type == "item_price":
            return {"item_price": parsed_prices[0]}

    return None


# Function to process all types of prices based on class_id
def process_price_by_class_id(shop_name, got_ocr_text, class_id):
    processed_price = None

    # Check class_id for the type of price
    if class_id == "item_price":
        price_type = "item_price"
    elif class_id == "item_member_price":
        price_type = "item_member_price"
    elif class_id == "item_initial_price":
        price_type = "item_initial_price"
    else:
        return None

    # Dispatch based on shop_name and price_type
    if shop_name == "EsoMarket":
        processed_price = process_esomarket(got_ocr_text)
    elif shop_name == "Penny":
        processed_price = process_penny(got_ocr_text, price_type)
    elif shop_name == "Billa":
        processed_price = process_billa(got_ocr_text, price_type)
    elif shop_name in ["Albert Hypermarket", "Albert Supermarket"]:
        processed_price = process_albert_hypermarket(got_ocr_text, price_type)
    elif shop_name in ["Tesco Supermarket", "Tesco Hypermarket"]:
        processed_price = process_tesco_supermarket(got_ocr_text, price_type)
    elif shop_name == "Lidl":
        processed_price = process_lidl(got_ocr_text)
    elif shop_name == "Kaufland":
        processed_price = process_kaufland(got_ocr_text, price_type)
    elif shop_name in ["Flop Top", "Flop"]:
        processed_price = process_flop_top(got_ocr_text, price_type)
    elif shop_name == "Travel Free":
        processed_price = process_travel_free(got_ocr_text, price_type)
    elif shop_name == "CBA Potraviny":
        processed_price = process_cba_potraviny(got_ocr_text)
    elif shop_name == "Bene":
        processed_price = process_bene(got_ocr_text)
    elif shop_name == "CBA Premium":
        processed_price = process_cba_premium(got_ocr_text)
    elif shop_name == "Lidl Shop":
        processed_price = process_lidl_shop(got_ocr_text)
    elif shop_name == "CBA Market":
        processed_price = process_cba_market(got_ocr_text)
    elif shop_name == "Makro":
        processed_price = process_makro(got_ocr_text, price_type)
    elif shop_name == "Globus":
        processed_price = process_globus(got_ocr_text, price_type)
    elif shop_name == "Tamda Foods":
        processed_price = process_tamda_foods(got_ocr_text, price_type)
    elif shop_name == "Ratio":
        processed_price = process_ratio(got_ocr_text)

    return processed_price

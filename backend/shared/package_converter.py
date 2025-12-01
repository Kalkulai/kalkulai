# GEBINDE-UMRECHNUNG FÜR PDF
# Diese Funktion konvertiert Positionen von Basis-Einheiten (L, m², kg) zu Stück

import re
import math
from typing import Dict, Any, List, Optional, Tuple


def extract_package_size(product_name: str) -> Optional[Tuple[float, str]]:
    """
    Extract package size from product name
    
    Examples:
        "Dispersionsfarbe weiß, matt, 10 L" → (10.0, "L")
        "Abdeckvlies mit Anti-Rutsch, 1x10 m" → (10.0, "m²")
        "Kreppband 19mm, 50 m" → (50.0, "m")
        "Gips-Spachtelmasse, 10 kg" → (10.0, "kg")
        "Acryllack weiß, glänzend, 750 ml" → (0.75, "L")
    
    Returns:
        (size, unit) tuple or None
    """
    # IMPORTANT: Order matters! More specific patterns first!
    patterns = [
        # Specific patterns first
        (r'1x(\d+(?:\.\d+)?)\s*m\b', 'm²'),        # 1x10 m (Abdeckvlies) = m²
        (r'(\d+(?:\.\d+)?)\s*m²', 'm²'),           # 10 m²
        (r'(\d+(?:\.\d+)?)\s*qm\b', 'm²'),         # 10 qm
        (r'(\d+(?:\.\d+)?)\s*ml\b', 'ml'),         # 750 ml (convert to L later)
        (r'(\d+(?:\.\d+)?)\s*L\b', 'L'),           # 10 L, 10L
        (r'(\d+(?:\.\d+)?)\s*kg\b', 'kg'),         # 10 kg, 10kg
        (r'(\d+(?:\.\d+)?)\s*m\b', 'm'),           # 50 m (last, after ml!)
    ]
    
    for pattern, unit_type in patterns:
        match = re.search(pattern, product_name, re.IGNORECASE)
        if match:
            size = float(match.group(1))
            
            # Convert ml to L
            if unit_type == 'ml':
                return (size / 1000, 'L')
            
            return (size, unit_type)
    
    return None


def convert_to_package_units(
    positions: List[Dict[str, Any]],
    catalog_by_name: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Convert positions from base units (L, m², kg) to package units (Stück)
    
    Args:
        positions: List of position dicts with menge, einheit, name
        catalog_by_name: Catalog lookup dict
    
    Returns:
        Converted positions with menge in Stück
    """
    converted = []
    
    for pos in positions:
        pos_copy = pos.copy()
        
        # Get position details
        required_amount = pos.get("menge", 0)
        required_unit = (pos.get("einheit") or "").strip().lower()
        product_name = pos.get("name", "")
        
        # Skip if already in Stück or no conversion needed
        if required_unit in ["stück", "stuck", "stk", "piece", ""]:
            pos_copy["einheit"] = "Stück"
            converted.append(pos_copy)
            continue
        
        # Try to get catalog entry
        catalog_entry = catalog_by_name.get(product_name.lower())
        
        # Extract package size from product name
        package_info = extract_package_size(product_name)
        
        if not package_info:
            # No package info found, keep as-is
            converted.append(pos_copy)
            continue
        
        package_size, package_unit = package_info
        
        # Normalize units for comparison
        unit_map = {
            'l': 'L',
            'liter': 'L',
            'kg': 'kg',
            'kilogramm': 'kg',
            'm': 'm',
            'meter': 'm',
            'm²': 'm²',
            'm2': 'm²',
            'qm': 'm²',
            'quadratmeter': 'm²',
        }
        
        required_unit_norm = unit_map.get(required_unit, required_unit)
        package_unit_norm = unit_map.get(package_unit.lower(), package_unit)
        
        # Check if units match
        if required_unit_norm == package_unit_norm:
            # Calculate number of packages needed
            packages_needed = required_amount / package_size
            
            # Round up to full packages (can't buy 0.5 Eimer)
            packages_needed_rounded = math.ceil(packages_needed)
            
            # Update position
            pos_copy["menge"] = packages_needed_rounded
            pos_copy["einheit"] = "Stück"
            pos_copy["_original_menge"] = required_amount
            pos_copy["_original_einheit"] = pos.get("einheit")
            pos_copy["_package_size"] = package_size
            pos_copy["_package_unit"] = package_unit
            
            converted.append(pos_copy)
        else:
            # Units don't match, keep as-is
            converted.append(pos_copy)
    
    return converted


# TESTING
if __name__ == "__main__":
    # Test extract_package_size
    test_products = [
        "Dispersionsfarbe weiß, matt, 10 L",
        "Tiefengrund lösemittelfrei, 10 L",
        "Abdeckvlies mit Anti-Rutsch, 1x10 m",
        "Kreppband 19mm, 50 m",
        "Gips-Spachtelmasse, 10 kg",
        "Acryllack weiß, glänzend, 750 ml",
    ]
    
    print("=== Testing Package Size Extraction ===\n")
    for product in test_products:
        info = extract_package_size(product)
        print(f"{product}")
        print(f"  → {info}\n")
    
    # Test convert_to_package_units
    print("\n=== Testing Position Conversion ===\n")
    
    positions = [
        {"name": "Tiefengrund lösemittelfrei, 10 L", "menge": 5, "einheit": "L", "einzelpreis": 24.90},
        {"name": "Dispersionsfarbe weiß, matt, 10 L", "menge": 35, "einheit": "L", "einzelpreis": 29.90},
        {"name": "Abdeckvlies mit Anti-Rutsch, 1x10 m", "menge": 21, "einheit": "m²", "einzelpreis": 27.90},
        {"name": "Kreppband 19mm, Standard", "menge": 20, "einheit": "m", "einzelpreis": 2.90},
    ]
    
    catalog = {}  # Not needed for name-based extraction
    
    converted = convert_to_package_units(positions, catalog)
    
    for pos in converted:
        print(f"{pos['name']}")
        print(f"  Original: {pos.get('_original_menge', pos['menge'])} {pos.get('_original_einheit', pos['einheit'])}")
        print(f"  Converted: {pos['menge']} {pos['einheit']}")
        if '_package_size' in pos:
            print(f"  Package: {pos['_package_size']} {pos['_package_unit']}")
        print()
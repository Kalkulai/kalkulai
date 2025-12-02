#!/usr/bin/env python3
"""
Test-Skript für Voice Input Konfiguration.

Prüft, ob Azure Speech Services korrekt konfiguriert ist.
"""

import os
import sys
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    BASE_DIR = Path(__file__).resolve().parent
    load_dotenv(BASE_DIR / ".env")
except Exception:
    pass

def test_voice_config():
    """Teste die Voice Input Konfiguration."""
    print("🔍 Prüfe Voice Input Konfiguration...\n")
    
    # Prüfe Umgebungsvariablen
    azure_key = os.getenv("AZURE_SPEECH_KEY", "").strip()
    azure_region = os.getenv("AZURE_SPEECH_REGION", "westeurope").strip()
    
    print(f"AZURE_SPEECH_KEY: {'✅ Gesetzt' if azure_key else '❌ NICHT gesetzt'}")
    print(f"AZURE_SPEECH_REGION: {azure_region if azure_region else '❌ NICHT gesetzt'}")
    print()
    
    if not azure_key:
        print("❌ FEHLER: AZURE_SPEECH_KEY ist nicht gesetzt!")
        print("\n📝 So behebst du das Problem:")
        print("1. Erstelle eine Azure Speech Services Ressource im Azure Portal")
        print("2. Kopiere den Key aus der Ressource")
        print("3. Füge folgende Zeile zu backend/.env hinzu:")
        print("   AZURE_SPEECH_KEY=dein-key-hier")
        print("4. Optional: Setze die Region (Standard: westeurope):")
        print("   AZURE_SPEECH_REGION=westeurope")
        print("\n🔗 Azure Portal: https://portal.azure.com")
        return False
    
    # Teste Backend-Endpoint (wenn Backend läuft)
    try:
        import httpx
        response = httpx.get("http://localhost:7860/api/speech/config", timeout=2.0)
        if response.status_code == 200:
            config = response.json()
            print("✅ Backend-Endpoint erreichbar")
            print(f"   enabled: {config.get('enabled')}")
            print(f"   region: {config.get('region')}")
            if config.get('enabled'):
                print("\n✅ Voice Input ist aktiviert und bereit!")
            else:
                print("\n⚠️  Backend meldet, dass Voice Input nicht aktiviert ist.")
                print("   Stelle sicher, dass das Backend neu gestartet wurde nach dem Setzen der Umgebungsvariablen.")
        else:
            print(f"⚠️  Backend-Endpoint antwortet mit Status {response.status_code}")
    except httpx.ConnectError:
        print("⚠️  Backend läuft nicht oder ist nicht erreichbar auf http://localhost:7860")
        print("   Starte das Backend mit: python main.py")
    except ImportError:
        print("⚠️  httpx nicht installiert - kann Backend-Endpoint nicht testen")
    except Exception as e:
        print(f"⚠️  Fehler beim Testen des Backend-Endpoints: {e}")
    
    print()
    return True

if __name__ == "__main__":
    success = test_voice_config()
    sys.exit(0 if success else 1)


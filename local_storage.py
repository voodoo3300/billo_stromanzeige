import json
import os
from datetime import datetime
default_dict = {
                        'cum_counter_start_value': None,
                        'cum_counter_start_time': None,
                    }
class DataHandler:
    def __init__(self, filename='data.json'):
        self.filename = filename
        self.data = self.__load_data()

    def __load_data(self):
        """Lädt Daten aus einer JSON-Datei, erstellt eine Datei, wenn sie nicht existiert, und fängt mögliche Fehler ab."""
        try:
            if not os.path.exists(self.filename):
                with open(self.filename, 'w') as file:
                    json.dump(default_dict, file)  # Leeres JSON-Objekt in die Datei schreiben
                return default_dict
            else:
                with open(self.filename, 'r') as file:
                    return json.load(file)
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")  # Log den Fehler
            return default_dict  # Rückgabe eines leeren Dicts, wenn das Laden fehlschlägt
        except Exception as e:
            print(f"General error when accessing file: {e}")
            return default_dict  # Sicherstellen, dass immer ein Dict zurückgegeben wird

    def __save_data(self):
        """Speichert Daten in einer JSON-Datei, mit Fehlerbehandlung."""
        try:
            with open(self.filename, 'w') as file:
                json.dump(self.data, file)
        except Exception as e:
            print(f"Error saving data to file: {e}")

    def set_data(self, value):
        self.data = {
                        'cum_counter_start_value': value,
                        'cum_counter_start_time': datetime.now().strftime("%d.%m.%Y, %H:%Mh")
                    }
        self.__save_data()
    def reset_data(self):
        self.data = default_dict
        self.__save_data()

        


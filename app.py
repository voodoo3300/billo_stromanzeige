import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests
from influxdb_client import InfluxDBClient
from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout,
                             QLabel, QLCDNumber, QProgressBar, QPushButton,
                             QSizePolicy, QSpacerItem, QStackedWidget,
                             QVBoxLayout, QWidget, QGroupBox)
from PyQt5.QtGui import QFont

from dotenv import load_dotenv
import os




class DataThread(QThread):
    # Signal zum Senden der Daten an das Hauptfenster
    dataFetched = pyqtSignal(dict)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        client = InfluxDBClient(url=os.environ.get("influx_url"),
                                token=os.environ.get("influx_token"), org=os.environ.get("influx_org"))
        query_api = client.query_api()
        query = '''
dataWattage = from(bucket: "Strom")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "vz_measurement")
  |> filter(fn: (r) => r["_field"] == "value")
  |> filter(fn: (r) => r["uuid"] == "1810eb97-3799-46d8-9764-2ab1c4ea7cb4")
  |> group(columns: ["uuid"])

dataCounter = from(bucket: "Strom")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "vz_measurement")
  |> filter(fn: (r) => r["_field"] == "value")
  |> filter(fn: (r) => r["uuid"] == "22792059-416a-4117-8b3a-420e34a841a1")
  |> group(columns: ["uuid"])
  |> last()
  |> set(key: "_field", value: "currentCounter")


minValue = dataWattage
  |> min()
  |> set(key: "_field", value: "minValue")

maxValue = dataWattage
  |> max()
  |> set(key: "_field", value: "maxValue")

avgValue = dataWattage
  |> mean()
  |> set(key: "_field", value: "avgValue")

latestValue = dataWattage
  |> last()
  |> set(key: "_field", value: "latestValue")

// Kombinieren von Min und Max
union(tables: [minValue, maxValue, avgValue, latestValue, dataCounter])
'''
        result = query_api.query(query=query)
        data_dict = {}

        for table in result:
            for record in table.records:
                # Verwende _field als Schlüssel im Dictionary
                field_key = record.get_field()  # Dies könnte 'minValue', 'maxValue' oder 'currentCounter' sein, je nachdem wie Sie 'set' in Ihrer Flux-Abfrage verwenden
                if field_key:
                    data_dict[field_key] = {
                        '_time': record.get_time(),
                        '_value': record.get_value(),
                        '_measurement': record.get_measurement(),
                        'uuid': record.values.get('uuid')
                    }

        client.close()
        self.dataFetched.emit(data_dict)


class MyApp(QWidget):
    def __init__(self, kiosk_mode=False):
        super().__init__()
        if kiosk_mode:
            # Setze das Fenster in den Vollbildmodus und entferne die Dekoration
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowFullScreen)
        self.initUI()

    def initUI(self):
        self.setGeometry(100, 100, 800, 400)
        self.setWindowTitle('Pimmelzähler Info Display')

        # Zählerstand
        self.lcd_zaehlerstand = QLCDNumber(self)
        self.lcd_zaehlerstand.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Anzahl der Ziffern, die angezeigt werden können
        self.lcd_zaehlerstand.setDigitCount(10)
        self.lcd_zaehlerstand.display(888888888)  # Beispielwert

        self.lcd_current = QLCDNumber(self)
        self.lcd_current.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Anzahl der Ziffern, die angezeigt werden können
        self.lcd_current.setDigitCount(5)
        self.lcd_current.display(88888)  # Beispielwert
        self.ts_label_current = QLabel('Warten auf Daten')

        # Hauptlayout
        layout = QHBoxLayout(self)

        # Container für das Stacked Widget und die ProgressBar
        middle_container = QWidget(self)
        middle_layout = QVBoxLayout(middle_container)

        # Stacked Widget
        self.stackedWidget = QStackedWidget(self)

        content_layout1 = self.create_page('Zählerstand')
        content_layout1.addWidget(QLabel('kWh'), alignment=Qt.AlignRight)
        content_layout1.addWidget(self.lcd_zaehlerstand)
        content_layout1.addWidget(QLabel('Letzte Aktualisierung'))

        content_layout2 = self.create_page('Leistunfsaufnahme')
        content_layout2.addWidget(QLabel('W'), alignment=Qt.AlignRight)
        content_layout2.addWidget(self.lcd_current)
        content_layout2.addWidget(self.ts_label_current)

        content_layout3 = self.create_page('Tagesstatistik')

        #self.lcd_min = QLCDNumber(self)
        #self.lcd_max = QLCDNumber(self)
        #self.lcd_avg = QLCDNumber(self)
        #self.lcd_w24 = QLCDNumber(self)
        #self.lcd_wtoday = QLCDNumber(self)
        #self.label_c24 = QLabel('---,--- €')
        #self.label_ctoday = QLabel('---,--- €')

        p3_top_container = QWidget(self)
        p3_top_layout = QVBoxLayout(p3_top_container)

        self.groupBoxMin = QGroupBox("Min")
        verticalLayoutMin = QVBoxLayout(self.groupBoxMin)
        self.lcdNumberMin = QLCDNumber(self.groupBoxMin)
        verticalLayoutMin.addWidget(self.lcdNumberMin)
        p3_top_layout.addWidget(self.groupBoxMin)

        # QGroupBox für Max-Wert
        self.groupBoxMax = QGroupBox("Max")
        verticalLayoutMax = QVBoxLayout(self.groupBoxMax)
        self.lcdNumberMax = QLCDNumber(self.groupBoxMax)
        verticalLayoutMax.addWidget(self.lcdNumberMax)
        p3_top_layout.addWidget(self.groupBoxMax)

        # QGroupBox für Avg-Wert
        self.groupBoxAvg = QGroupBox("Avg")
        verticalLayoutAvg = QVBoxLayout(self.groupBoxAvg)
        self.lcdNumberAvg = QLCDNumber(self.groupBoxAvg)
        self.lcdNumberAvg.setDigitCount(5)
        self.lcdNumberAvg.display(88888)  # Beispielwert
        self.lcdNumberAvg.setSegmentStyle(QLCDNumber.Filled)
        self.lcdNumberAvg.setMinimumHeight(100)
        verticalLayoutAvg.addWidget(self.lcdNumberAvg)
        p3_top_layout.addWidget(self.groupBoxAvg)

        groupBox = QGroupBox("GroupBox", self)  # Titel der GroupBox kann angepasst werden
        gridLayout = QGridLayout(groupBox)

        # Verbrauch heute
        labelToday = QLabel("Verbrauch heute")
        gridLayout.addWidget(labelToday, 0, 0)

        lcdNumberToday = QLCDNumber()
        gridLayout.addWidget(lcdNumberToday, 0, 1)

        labelTodayUnit = QLabel("kWh")
        gridLayout.addWidget(labelTodayUnit, 0, 2)

        labelTodayCost = QLabel("12,90 €")
        labelTodayCost.setFont(QFont("Arial", 14))
        gridLayout.addWidget(labelTodayCost, 0, 3)

        # Verbrauch letzte 24 Stunden
        label24h = QLabel("Verbrauch 24h ")
        gridLayout.addWidget(label24h, 1, 0)

        lcdNumber24h = QLCDNumber()
        gridLayout.addWidget(lcdNumber24h, 1, 1)

        label24hUnit = QLabel("kWh")
        gridLayout.addWidget(label24hUnit, 1, 2)

        label24hCost = QLabel("13,87 €")
        label24hCost.setFont(QFont("Arial", 12))
        gridLayout.addWidget(label24hCost, 1, 3)



        





        content_label3 = QLabel('Weitere Informationen auf Seite 3.')
        content_layout3.addWidget(p3_top_container)
        content_layout3.addWidget(groupBox)
        middle_layout.addWidget(self.stackedWidget)

        # ProgressBar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(100)
        middle_layout.addWidget(self.progress_bar)

        # Button links
        self.btn_left = QPushButton('←', self)
        self.btn_left.setFixedSize(100, 400)
        layout.addWidget(self.btn_left)

        # Fügen Sie das mittlere Container-Widget hinzu
        layout.addWidget(middle_container)

        # Button rechts
        self.btn_right = QPushButton('→', self)
        self.btn_right.setFixedSize(100, 400)
        layout.addWidget(self.btn_right)

        # Button-Funktionalitäten
        self.btn_left.clicked.connect(self.show_previous_page)
        self.btn_right.clicked.connect(self.show_next_page)

        # Timer für Datenaktualisierung
        self.timer = QTimer()
        self.timer.setInterval(10000)  # Aktualisierung alle 10 Sekunden
        # self.timer.timeout.connect(self.fetch_data)
        self.timer.start()

        # Fortschrittsbalken-Timer: Aktualisiert die ProgressBar jede Sekunde
        self.progress_value = 0
        self.progress_timer = QTimer(self)
        # 1000 Millisekunden == 1 Sekunde
        self.progress_timer.setInterval(1000)
        self.progress_timer.timeout.connect(self.update_progress_bar)
        self.progress_timer.start()

        # Thread für Netzwerkanfragen
        self.dataThread = DataThread(
            "http://localhost:5000/api/energy/consumption")
        self.dataThread.dataFetched.connect(self.update_display)

    def show_previous_page(self):
        index = self.stackedWidget.currentIndex()
        if index > 0:
            self.stackedWidget.setCurrentIndex(index - 1)

    def show_next_page(self):
        index = self.stackedWidget.currentIndex()
        if index < self.stackedWidget.count() - 1:
            self.stackedWidget.setCurrentIndex(index + 1)

    def fetch_data(self):
        print()

    def update_progress_bar(self):
        if self.progress_value < 100:
            self.progress_value += 10  # Erhöht um 10% jede Sekunde

        else:
            self.progress_value = 0
            if not self.dataThread.isRunning():
                self.dataThread.start()
        self.progress_bar.setValue(self.progress_value)

    def update_display(self, data):
        # Aktualisieren Sie hier Ihre Info-Displays basierend auf den empfangenen Daten
        # self.page1.setText(str(data))  # Beispiel zur Anzeige der Daten
        print(str(data))
        self.lcd_zaehlerstand.display(
            int(data["currentCounter"]["_value"]))
        self.lcd_current.display(
            int(data["latestValue"]["_value"]))
        self.ts_label_current.setText(self.__convert_to_local_time(data["currentCounter"]["_time"], "Datensatz vom"))
        print(self.__convert_to_local_time(data["currentCounter"]["_time"]))

    def __convert_to_local_time(self, utc_time, prefix=None, suffix=None):
        # Angenommen, data["currentCounter"]["_time"] ist ein datetime-Objekt in UTC
        utc_time = utc_time.replace(tzinfo=timezone.utc)

        # Konvertierung in die Zeitzone 'Europe/Berlin'
        berlin_time = utc_time.astimezone(ZoneInfo("Europe/Berlin"))
        berlin_time.strftime('%d.%m.%Y %H:%M:%S')

        if prefix is not None:
            berlin_time = f"{prefix} {berlin_time}"

        if suffix is not None:
            berlin_time = f"{suffix} {berlin_time}"

        # Formatierung des Datums in deutschem Format
        return berlin_time

    def create_page(self, title):
        page = QWidget()
        page_layout = QVBoxLayout(page)

        # Überschrift
        header = QLabel(title)
        header.setStyleSheet('font-size: 18px; font-weight: bold;')
        page_layout.addWidget(header)

        # Trennlinie
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        page_layout.addWidget(line)

        # Inhalt-Layout (flexibel für weitere Widgets)
        content_layout = QVBoxLayout()

        # Spacer, der den Inhalt nach unten drückt
        spacer = QSpacerItem(20, 40, QSizePolicy.Minimum,
                             QSizePolicy.Expanding)
        page_layout.addSpacerItem(spacer)

        # Fügt das Inhalt-Layout hinzu, das sich anpassen kann, um den verbleibenden Platz zu füllen
        page_layout.addLayout(content_layout)

        self.stackedWidget.addWidget(page)
        return content_layout  # Gibt das Layout für Inhalte zurück


if __name__ == '__main__':
    load_dotenv()
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    kiosk_mode = '--kiosk' in sys.argv

    ex = MyApp(kiosk_mode=kiosk_mode)
    ex.show()
    sys.exit(app.exec_())

import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import matplotlib.dates as mdates
import matplotlib.ticker as ticker
import qdarkstyle
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient
from matplotlib.backends.backend_qt5agg import \
    FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QFontDatabase
from PyQt5.QtWidgets import (QApplication, QFrame, QGridLayout, QGroupBox,
                             QHBoxLayout, QLabel, QLCDNumber, QProgressBar,
                             QPushButton, QSizePolicy, QSpacerItem,
                             QStackedWidget, QVBoxLayout, QWidget)

from local_storage import DataHandler
import matplotlib.pyplot as plt

plt.style.use('dark_background')
glow_style = """
QLabel {
    color: #f8f8f2;
    background-color: #44475a;
    border: 2px solid #6272a4;
    padding: 5px;
    border-radius: 10px;
    text-shadow: 0 0 10px rgba(255, 255, 255, 0.7);
}
"""
def watt_formatter(x, pos):
    return f"{int(x)} W"

def load_stylesheet(file_path):
    """Lädt ein Stylesheet aus einer Datei in einen String."""
    try:
        with open(file_path, "r") as file:
            return file.read()
    except IOError:
        print("Stylesheet-Datei konnte nicht geladen werden.")
        return ""


class DataThread(QThread):
    # Signal zum Senden der Daten an das Hauptfenster
    dataFetched = pyqtSignal(dict)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        client = InfluxDBClient(
            url=os.environ.get("influx_url"),
            token=os.environ.get("influx_token"),
            org=os.environ.get("influx_org"),
        )
        query_api = client.query_api()
        query = """
import "date"

dataWattage = from(bucket: "Strom")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "vz_measurement")
  |> filter(fn: (r) => r["_field"] == "value")
  |> filter(fn: (r) => r["uuid"] == "1810eb97-3799-46d8-9764-2ab1c4ea7cb4")
  |> group(columns: ["uuid"])

// Tageszähler (Bezug)
dataCounter = from(bucket: "Strom")
  |> range(start: date.truncate(t: now(), unit: 1d), stop: now())
  |> filter(fn: (r) => r["_measurement"] == "vz_measurement")
  |> filter(fn: (r) => r["_field"] == "value")
  |> filter(fn: (r) => r["uuid"] == "22792059-416a-4117-8b3a-420e34a841a1")
  |> group(columns: ["uuid"])

// Tageszähler (Einspeisung)
dataCounterDeliver = from(bucket: "Strom")
  |> range(start: date.truncate(t: now(), unit: 1d), stop: now())
  |> filter(fn: (r) => r["_measurement"] == "vz_measurement")
  |> filter(fn: (r) => r["_field"] == "value")
  |> filter(fn: (r) => r["uuid"] == "86ef6af6-c13a-4084-beed-6183b44c0a17")
  |> group(columns: ["uuid"])

// ---- Autoencoder: letzter Fehler ----
latestError = from(bucket: "Strom")
  |> range(start: -10m)
  |> filter(fn: (r) => r["_measurement"] == "vz_measurement")
  |> filter(fn: (r) => r["_field"] == "error")
  |> filter(fn: (r) => r["uuid"] == "1810eb97-3799-46d8-9764-2ab1c4ea7cb4")
  |> last()
  |> set(key: "_field", value: "latestError")

// ---- Autoencoder: aktueller Anomaly-Indikator (0/1) ----
latestAnomaly = from(bucket: "Strom")
  |> range(start: -10m)
  |> filter(fn: (r) => r["_measurement"] == "vz_measurement")
  |> filter(fn: (r) => r["_field"] == "anomaly")
  |> filter(fn: (r) => r["uuid"] == "1810eb97-3799-46d8-9764-2ab1c4ea7cb4")
  |> last()
  |> set(key: "_field", value: "latestAnomaly")

// ---- Autoencoder: War in den letzten 5 Minuten eine Anomalie? ----
recentAnomaly = from(bucket: "Strom")
  |> range(start: -5m)
  |> filter(fn: (r) => r["_measurement"] == "vz_measurement")
  |> filter(fn: (r) => r["_field"] == "anomaly")
  |> filter(fn: (r) => r["uuid"] == "1810eb97-3799-46d8-9764-2ab1c4ea7cb4")
  |> max()            // wenn max == 1 → es gab eine Anomalie
  |> set(key: "_field", value: "recentAnomaly")

// ---- Bestehende Werte ----
latestCounterDelivery = dataCounterDeliver |> last() |> set(key: "_field", value: "currentCounterDelivery")
latestCounter = dataCounter |> last() |> set(key: "_field", value: "currentCounter")
startCounter = dataCounter |> first() |> set(key: "_field", value: "startofdayCounter")
minValue = dataWattage |> min() |> set(key: "_field", value: "minValue")
maxValue = dataWattage |> max() |> set(key: "_field", value: "maxValue")
avgValue = dataWattage |> mean() |> set(key: "_field", value: "avgValue")
latestValue = dataWattage |> last() |> set(key: "_field", value: "latestValue")

// ---- Alle Werte zusammenführen ----
union(tables: [
  minValue,
  maxValue,
  avgValue,
  latestValue,
  latestCounter,
  startCounter,
  latestCounterDelivery,
  latestError,
  latestAnomaly,
  recentAnomaly
])
"""
        result = query_api.query(query=query)
        data_dict = {}

        for table in result:
            for record in table.records:
                # Verwende _field als Schlüssel im Dictionary
                field_key = (
                    record.get_field()
                )  # Dies könnte 'minValue', 'maxValue' oder 'currentCounter' sein, je nachdem wie Sie 'set' in Ihrer Flux-Abfrage verwenden
                if field_key:
                    data_dict[field_key] = {
                        "_time": record.get_time(),
                        "_value": record.get_value(),
                        "_measurement": record.get_measurement(),
                        "uuid": record.values.get("uuid"),
                    }

        client.close()
        self.dataFetched.emit(data_dict)

class PlotDataThread(QThread):
    dataFetchedForPlot = pyqtSignal(list, list)  # x, y Werte für Plot

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        client = InfluxDBClient(
            url=os.environ.get("influx_url"),
            token=os.environ.get("influx_token"),
            org=os.environ.get("influx_org"),
        )
        query_api = client.query_api()
        query = """
from(bucket: "Strom")
  |> range(start: -12h)
  |> filter(fn: (r) => r["_measurement"] == "vz_measurement")
  |> filter(fn: (r) => r["_field"] == "value")
  |> filter(fn: (r) => r["uuid"] == "1810eb97-3799-46d8-9764-2ab1c4ea7cb4")
  |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
"""
        result = query_api.query(query=query)
        x_data = []
        y_data = []
        for table in result:
            for record in table.records:
                x_data.append(record.get_time())
                y_data.append(record.get_value())

        client.close()
        x_data = [self.__convert_utc_to_local(x) for x in x_data]
        self.dataFetchedForPlot.emit(x_data, y_data)

    def __convert_utc_to_local(self, utc_time):
        # Stelle sicher, dass die Zeit als UTC markiert ist
        utc_time = utc_time.replace(tzinfo=timezone.utc)

        # Konvertiere die Zeit in die gewünschte Zeitzone ('Europe/Berlin')
        local_time = utc_time.astimezone(ZoneInfo("Europe/Berlin"))
        return local_time

class MplCanvas(FigureCanvas):
    def __init__(self, parent=None, dpi=100):
        # Berechne die Größe in Zoll basierend auf der maximalen Pixelgröße und der DPI
        width_in_inches = 500 / dpi  # Max. 500 Pixel breit
        height_in_inches = 300 / dpi  # Max. 250 Pixel hoch
        
        # Erstelle eine Figur mit den berechneten Dimensionen
        fig = Figure(figsize=(width_in_inches, height_in_inches), dpi=dpi)
        self.axes = fig.add_subplot(111)
        
        super(MplCanvas, self).__init__(fig)

class MyApp(QWidget):
    def __init__(self, kiosk_mode=False):
        super().__init__()
        if kiosk_mode:
            # Setze das Fenster in den Vollbildmodus und entferne die Dekoration
            self.showFullScreen()
            self.setWindowFlags(Qt.FramelessWindowHint)
        self.cumcounter = DataHandler()
        self.zaehlerstand = 0
        self.zaehlerstand_ein = 0
        self.canvas = MplCanvas(self, dpi=100)
        self.initUI()

    def initUI(self):

        self.setGeometry(100, 100, 800, 400)
        self.setWindowTitle("Pimmelzähler Info Display")
        font_id = QFontDatabase.addApplicationFont(
            "wwDigital.ttf")  # Pfad zur Schriftartdatei
        font_name = QFontDatabase.applicationFontFamilies(
            font_id)[0]  # Name der geladenen Schriftart
        # Größe der Schriftart festlegen
        self.custom_si_font = QFont(font_name, 14)
        self.custom_info_font = QFont(font_name, 9)
        self.ts_label_current = QLabel("Warten auf Daten")
        self.ts_label_current.setFont(self.custom_info_font)
        self.ts_label_counter = QLabel("Warten auf Daten")
        self.ts_label_counter.setFont(self.custom_info_font)
        # Zählerstand
        self.lcd_zaehlerstand = QLCDNumber(self)
        self.lcd_zaehlerstand.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        # Anzahl der Ziffern, die angezeigt werden können
        self.lcd_zaehlerstand.setDigitCount(6)
        self.lcd_zaehlerstand.display(000000)  # Beispielwert



        # Zählerstand
        self.lcd_zaehlerstand_ein = QLCDNumber(self)
        self.lcd_zaehlerstand_ein.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        # Anzahl der Ziffern, die angezeigt werden können
        self.lcd_zaehlerstand_ein.setDigitCount(6)
        self.lcd_zaehlerstand_ein.display(000000)  # Beispielwert

        self.lcd_kulm = QLCDNumber(self)
        self.lcd_kulm.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        # Anzahl der Ziffern, die angezeigt werden können
        self.lcd_kulm.setDigitCount(6)
        self.lcd_kulm.display(0)  # Beispielwert

        self.lcd_current = QLCDNumber(self)
        self.lcd_current.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Anzahl der Ziffern, die angezeigt werden können
        self.lcd_current.setDigitCount(6)
        self.lcd_current.display(88888)  # Beispielwert

        # Hauptlayout
        layout = QHBoxLayout(self)

        # Container für das Stacked Widget und die ProgressBar
        middle_container = QWidget(self)
        middle_layout = QVBoxLayout(middle_container)

        # Stacked Widget
        self.stackedWidget = QStackedWidget(self)

        content_layout1 = self.create_page("Zählerstand Bezug")
        content_layout1.addWidget(self.get_si('kWh'), alignment=Qt.AlignRight)
        content_layout1.addWidget(self.lcd_zaehlerstand)
        content_layout1.addWidget(self.ts_label_counter)

        content_layout1a = self.create_page("Zählerstand Einspeisung")
        content_layout1a.addWidget(self.get_si('Wh'), alignment=Qt.AlignRight)
        content_layout1a.addWidget(self.lcd_zaehlerstand_ein)
        content_layout1a.addWidget(self.ts_label_counter)

        content_layout2 = self.create_page("Leistungsaufnahme")
        content_layout2.addWidget(self.get_si('W'), alignment=Qt.AlignRight)
        content_layout2.addWidget(self.lcd_current)
        content_layout2.addWidget(self.ts_label_current)

        content_layout3 = self.create_page("Tagesstatistik")

        # self.lcd_min = QLCDNumber(self)
        # self.lcd_max = QLCDNumber(self)
        # self.lcd_avg = QLCDNumber(self)
        # self.lcd_w24 = QLCDNumber(self)
        # self.lcd_wtoday = QLCDNumber(self)
        # self.label_c24 = QLabel('---,--- €')
        # self.label_ctoday = QLabel('---,--- €')

        p3_top_container = QWidget(self)
        p3_top_layout = QVBoxLayout(p3_top_container)

        groupBox = QGroupBox(
            "GroupBox", self
        )  # Titel der GroupBox kann angepasst werden
        gridLayout = QGridLayout(groupBox)

        # Verbrauch heute
        labelToday = QLabel("Verbrauch heute")
        gridLayout.addWidget(labelToday, 0, 0)

        self.consumptionToday = QLabel("----")
        self.consumptionToday.setStyleSheet(glow_style)
        self.consumptionToday.setFont(QFont(font_name, 20))
        gridLayout.addWidget(self.consumptionToday, 0, 1)

        gridLayout.addWidget(QLabel("kWh"), 0, 2)

        self.labelTodayCost = QLabel("")
        self.labelTodayCost.setStyleSheet(glow_style)
        self.labelTodayCost.setFont(QFont(font_name, 20))
        gridLayout.addWidget(self.labelTodayCost, 0, 3)
        gridLayout.addWidget(QLabel('€'), 0, 4)

        p3_top_layout.addWidget(groupBox)

        # QGroupBox für Max-Wert
        self.groupBoxMax = QGroupBox("MAX(P) der letzten 24h")
        verticalLayoutMax = QVBoxLayout(self.groupBoxMax)
        self.maxW = QLabel("12345 W")
        self.maxW.setFont(QFont("Arial", 12))

        self.groupBoxMin = QGroupBox("MIN(P) der letzten 24h")
        verticalLayoutMin = QVBoxLayout(self.groupBoxMin)
        self.minW = QLabel("12345 W")
        self.minW.setFont(QFont("Arial", 12))
        verticalLayoutMin.addWidget(self.minW)

        p3_top_layout.addWidget(self.groupBoxMax)

        # QGroupBox für Avg-Wert
        self.groupBoxAvg = QGroupBox("Ø(P) der letzten 24h")
        verticalLayoutAvg = QVBoxLayout(self.groupBoxAvg)
        self.avgW = QLabel("12345 W")
        self.avgW.setFont(QFont("Arial", 12))

        verticalLayoutAvg.addWidget(self.avgW)
        verticalLayoutMax.addWidget(self.maxW)
        p3_top_layout.addWidget(self.groupBoxMin)

        p3_top_layout.addWidget(self.groupBoxAvg)

        content_layout3.addWidget(p3_top_container)

        content_layout4 = self.create_page("Kumulativer Zähler")
        self.lable_cumstat = self.get_si('8888888888888888888888888888888')
        content_layout4.addWidget(self.lable_cumstat, alignment=Qt.AlignRight)

        controll_container_widget = QWidget(self)
        controll_container_layout = QHBoxLayout(controll_container_widget)
        self.startStopButton = QPushButton("Start / Stop")
        self.startStopButton.clicked.connect(self.startStopClicked)
        controll_container_layout.addWidget(self.startStopButton)

        content_layout4.addWidget(controll_container_widget)

        content_layout4.addWidget(self.lcd_kulm)

        content_layout5 = self.create_page("Verlauf")
    
        content_layout5.addWidget(self.canvas)

        middle_layout.addWidget(self.stackedWidget)

        # ProgressBar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setFormat("")
        middle_layout.addWidget(self.progress_bar)

        # Button links
        self.btn_left = QPushButton("←", self)
        self.btn_left.setFixedSize(100, 300)
        layout.addWidget(self.btn_left)

        # Fügen Sie das mittlere Container-Widget hinzu
        layout.addWidget(middle_container)

        # Button rechts
        self.btn_right = QPushButton("→", self)
        self.btn_right.setFixedSize(100, 300)
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
        self.progress_timer.setInterval(20)
        self.progress_timer.timeout.connect(self.update_progress_bar)
        self.progress_timer.start()

        # Thread für Netzwerkanfragen
        self.dataThread = DataThread(
            "http://localhost:5000/api/energy/consumption")
        self.dataThread.dataFetched.connect(self.update_display)
        self.plotDataThread = PlotDataThread("http://localhost:8086")
        self.plotDataThread.dataFetchedForPlot.connect(self.update_plot)
        self.start_plot_data_thread()
        self.plot_timer = QTimer(self)
        #self.plot_timer.setInterval(10000)
        self.plot_timer.setInterval(600000) 
        self.plot_timer.timeout.connect(self.start_plot_data_thread)
        self.plot_timer.start()


        

    def update_plot(self, x_data, y_data):
        # Hier kannst du die Daten in einem Matplotlib-Plot darstellen
        self.canvas.axes.clear()  # Vorhandene Daten im Plot löschen
        self.canvas.axes.plot(x_data, y_data)  # Daten als rote Linie plotten
        self.canvas.axes.xaxis.set_major_formatter(mdates.DateFormatter('%Hh', tz=ZoneInfo("Europe/Berlin")))
        self.canvas.axes.xaxis.set_major_locator(mdates.HourLocator(interval=1))
        self.canvas.axes.yaxis.set_major_formatter(ticker.FuncFormatter(watt_formatter))
        self.canvas.draw()

    def start_plot_data_thread(self):
        if not self.plotDataThread.isRunning():
            self.plotDataThread.start()

    def startStopClicked(self):
        # Funktion, die ausgelöst wird, wenn der "Start / Stop" Button geklickt wird
        if self.cumcounter.data.get('cum_counter_start_value', None) is not None and self.cumcounter.data.get('cum_counter_start_time', None) is not None:
            self.cumcounter.reset_data()
            self.lcd_kulm.display(0)
            self.lable_cumstat.setText(
                'Gestoppt')
        else:
            self.cumcounter.set_data(self.zaehlerstand)
            self.lable_cumstat.setText(
                'Gestartet...')
        



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

    def get_si(self, text):
        label = QLabel(text)
        label.setFont(self.custom_si_font)
        return label

    def update_progress_bar(self):
        if self.progress_value < 100:
            self.progress_value += 1  # Erhöht um 10% jede Sekunde

        else:
            self.progress_value = 0
            if not self.dataThread.isRunning():
                self.dataThread.start()
        self.progress_bar.setValue(self.progress_value)

    def update_display(self, data):
        # Aktualisieren Sie hier Ihre Info-Displays basierend auf den empfangenen Daten
        # self.page1.setText(str(data))  # Beispiel zur Anzeige der Daten
        self.zaehlerstand = data["currentCounter"]["_value"] / 1000
        self.zaehlerstand_ein = data["currentCounterDelivery"]["_value"] #/ 1000

        # Zählerstand
        self.lcd_zaehlerstand.display(
            int(self.zaehlerstand))

        self.lcd_zaehlerstand_ein.display(
            int(self.zaehlerstand_ein))

        # Leistung
        if data["latestAnomaly"]["_value"] == 1:
            self.lcd_current.setStyleSheet("QLCDNumber { color: yellow; }")
        else:
            self.lcd_current.setStyleSheet("QLCDNumber { color: white; }")

        self.lcd_current.display(int(data["latestValue"]["_value"]))

        # Kul
        if self.cumcounter.data.get('cum_counter_start_value', None) is not None and self.cumcounter.data.get('cum_counter_start_time', None) is not None:
            self.lcd_kulm.display(
                int(self.zaehlerstand - self.cumcounter.data.get('cum_counter_start_value')))
            self.lable_cumstat.setText(
                f"-> EUR {((self.zaehlerstand - self.cumcounter.data.get('cum_counter_start_value'))*.31):.2f} seit {self.cumcounter.data.get('cum_counter_start_time')} | kWh")
        else:
            self.lable_cumstat.setText('Gestoppt')

      

        self.ts_label_current.setText(
            self.__convert_to_local_time_str(
                data["latestValue"]["_time"], "Datensatz vom"
            )
        )

        self.ts_label_counter.setText(
            self.__convert_to_local_time_str(
                data["currentCounter"]["_time"], "Datensatz vom"
            )
        )
        
        today_total = (data["currentCounter"]["_value"] -
                       data["startofdayCounter"]["_value"]) / 1000
        self.minW.setText(f'{data["minValue"]["_value"]:.1f} W')
        self.maxW.setText(f'{data["maxValue"]["_value"]:.1f} W')
        self.avgW.setText(f'{data["avgValue"]["_value"]:.1f} W')
        self.consumptionToday.setText(f'{today_total:.1f}')
        self.labelTodayCost.setText(f'{(today_total * 0.31):.2f}')
    
    def __convert_to_local_time_str(self, utc_time, prefix=None, suffix=None):
        # Angenommen, data["currentCounter"]["_time"] ist ein datetime-Objekt in UTC
        utc_time = utc_time.replace(tzinfo=timezone.utc)

        # Konvertierung in die Zeitzone 'Europe/Berlin'
        berlin_time = utc_time.astimezone(ZoneInfo("Europe/Berlin"))
        berlin_time = berlin_time.strftime("%d.%m.%Y %H:%M:%S")

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
        header.setFont(self.custom_si_font)
        header.setStyleSheet("font-size: 24px")
        page_layout.addWidget(header)

        # Trennlinie
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        page_layout.addWidget(line)

        # Inhalt-Layout (flexibel für weitere Widgets)
        content_layout = QVBoxLayout()

        # Spacer, der den Inhalt nach unten drückt
        # spacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        # page_layout.addSpacerItem(spacer)

        # Fügt das Inhalt-Layout hinzu, das sich anpassen kann, um den verbleibenden Platz zu füllen
        page_layout.addLayout(content_layout)

        self.stackedWidget.addWidget(page)
        return content_layout  # Gibt das Layout für Inhalte zurück


if __name__ == "__main__":
    load_dotenv()
    app = QApplication(sys.argv)
    app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
    kiosk_mode = "--kiosk" in sys.argv

    ex = MyApp(kiosk_mode=kiosk_mode)
    ex.show()
    sys.exit(app.exec_())

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <ArduinoJson.h>
#include <DHT.h>

// DHT sensor setup
#define DHTPIN 2
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

// WiFi credentials
const char* ssid = "AndroidAP26ED";
const char* password = "12345678";

// Server details
const char* serverUrl = "http://192.168.43.81:8000/update";
// Data sending interval (milliseconds)
const unsigned long sendInterval = 60000;  // 1 minute
unsigned long lastSendTime = 0;

// LED pin for status indication
const int ledPin = LED_BUILTIN;

void setup() {
  // Initialize serial
  Serial.begin(115200);
  Serial.println("\nWeather Station Starting...");
  
  // Initialize LED
  pinMode(ledPin, OUTPUT);
  digitalWrite(ledPin, HIGH);  // LED off initially (LED_BUILTIN is active LOW)
  
  // Initialize DHT sensor
  dht.begin();
  Serial.println("DHT sensor initialized");
  
  // Connect to WiFi
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  
  while (WiFi.status() != WL_CONNECTED) {
    digitalWrite(ledPin, LOW);   // LED on during connection
    delay(250);
    digitalWrite(ledPin, HIGH);  // LED off
    delay(250);
    Serial.print(".");
  }
  
  Serial.println();
  Serial.print("Connected to WiFi. IP address: ");
  Serial.println(WiFi.localIP());
  
  // Blink LED rapidly to indicate successful connection
  for (int i = 0; i < 5; i++) {
    digitalWrite(ledPin, LOW);
    delay(100);
    digitalWrite(ledPin, HIGH);
    delay(100);
  }
}

void loop() {
  unsigned long currentTime = millis();
  
  // Check if it's time to send data
  if (currentTime - lastSendTime >= sendInterval || lastSendTime == 0) {
    // Check WiFi connection
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("WiFi connection lost. Reconnecting...");
      WiFi.reconnect();
      
      // Wait for reconnection
      int attempt = 0;
      while (WiFi.status() != WL_CONNECTED && attempt < 20) {
        digitalWrite(ledPin, LOW);
        delay(100);
        digitalWrite(ledPin, HIGH);
        delay(100);
        Serial.print(".");
        attempt++;
      }
      
      if (WiFi.status() != WL_CONNECTED) {
        Serial.println("Failed to reconnect to WiFi. Will try again later.");
        return;
      }
      
      Serial.println("Reconnected to WiFi");
    }
    
    // Read sensor data
    float humidity = dht.readHumidity();
    float temperature = dht.readTemperature();
    
    // Check if readings are valid
    if (isnan(humidity) || isnan(temperature)) {
      Serial.println("Failed to read from DHT sensor!");
      
      // Blink LED to indicate sensor error
      for (int i = 0; i < 3; i++) {
        digitalWrite(ledPin, LOW);
        delay(200);
        digitalWrite(ledPin, HIGH);
        delay(200);
      }
      
      return;
    }
    
    // Print readings to serial
    Serial.print("Temperature: ");
    Serial.print(temperature);
    Serial.print(" °C, Humidity: ");
    Serial.print(humidity);
    Serial.println(" %");
    
    // Send data to server
    sendData(temperature, humidity);
    
    // Update last send time
    lastSendTime = currentTime;
  }
  
  // Small delay to prevent excessive loop iterations
  delay(100);
}

void sendData(float temperature, float humidity) {
  // Turn on LED to indicate data transmission
  digitalWrite(ledPin, LOW);
  
  WiFiClient client;
  HTTPClient http;
  
  // Connect to server
  http.begin(client, serverUrl);
  http.addHeader("Content-Type", "application/json");
  
  // Create JSON document
  StaticJsonDocument<200> doc;
  doc["temp"] = temperature;
  doc["hum"] = humidity;
  
  // Add battery level if you have a battery-powered setup
  // Uncomment and modify this if you're measuring battery level
  // float batteryLevel = readBatteryLevel();
  // doc["battery"] = batteryLevel;
  
  // Serialize JSON to string
  String jsonString;
  serializeJson(doc, jsonString);
  
  // Send POST request
  int httpResponseCode = http.POST(jsonString);
  
  // Check response
  if (httpResponseCode > 0) {
    String response = http.getString();
    Serial.print("HTTP Response code: ");
    Serial.println(httpResponseCode);
    Serial.print("Response: ");
    Serial.println(response);
    
    // Successfully sent data - blink LED once
    digitalWrite(ledPin, HIGH);
    delay(100);
    digitalWrite(ledPin, LOW);
    delay(100);
  } else {
    Serial.print("Error sending HTTP request. Error code: ");
    Serial.println(httpResponseCode);
    
    // Failed to send data - blink LED twice rapidly
    for (int i = 0; i < 2; i++) {
      digitalWrite(ledPin, HIGH);
      delay(100);
      digitalWrite(ledPin, LOW);
      delay(100);
    }
  }
  
  // Close connection
  http.end();
  
  // Turn off LED
  digitalWrite(ledPin, HIGH);
}

// Uncomment and implement this if you're measuring battery level
/*
float readBatteryLevel() {
  // Read analog value from battery monitoring pin
  // For example, if connected to A0:
  int rawValue = analogRead(A0);
  
  // Convert to voltage (assuming 3.3V reference and voltage divider if needed)
  // Adjust the formula based on your specific hardware setup
  float voltage = rawValue * (3.3 / 1023.0) * 2.0;  // Example for a voltage divider
  
  // Convert to percentage (assuming 3.7V max for LiPo, 3.0V min)
  float percentage = (voltage - 3.0) / (3.7 - 3.0) * 100.0;
  
  // Constrain to 0-100%
  percentage = constrain(percentage, 0.0, 100.0);
  
  return percentage;
}
*/

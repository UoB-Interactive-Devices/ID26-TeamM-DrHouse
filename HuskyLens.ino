#include "HUSKYLENS.h"
#include "Wire.h"
#include <WiFi.h> // --- NEW: Wi-Fi Library ---

HUSKYLENS huskylens;

// ==========================================
// --- THE MASTER SWITCH ---
// Set to true for Wi-Fi. Set to false for USB Cable!
bool useWiFi = false; 
// ==========================================

// --- NEW: Wi-Fi Settings (THE ROBOT IS NOW THE ROUTER) ---
const char* ap_ssid = "Tank_Robot";
const char* ap_pass = "12345678";

// When a laptop connects to an ESP32, it almost ALWAYS gets this IP:
const char* hostIP = "192.168.4.2"; 
const uint16_t port = 5204;
WiFiClient client;

// --- Motor Wiring ---
int ENA = 32; int IN1 = 33; int IN2 = 25; 
int ENB = 14; int IN3 = 26; int IN4 = 27; 

// --- Joystick Pins ---
int joyXPin = 35; 
int joyYPin = 34; 

// --- TANK STEERING SETTINGS: THE LOW RIDER TEST ---
int autoBaseSpeed = 85;         // The absolute crawl. 

// SOFT TURNS
int autoSoftInner = 85;         // Pushing the floor!
int autoSoftOuter = 110;        // Just enough difference to steer

// HARD TURNS 
int autoHardPush = 120;         // Push forward harder into the turn!
int autoHardRev = -120;         // Pull backward gently just to help pivot

// --- Odometry Variables ---
float posX = 0.0, posY = 0.0, heading = 1.5708;
float moveDistance = 2.0; 

// --- LINE TRACKING MEMORY & DIAGNOSTICS ---
unsigned long lastDetectionTime = 0;
const unsigned long MEMORY_TIMEOUT = 200; 
int robotState = 0; // 0=Stop, 1=Strt, 2=SoftL, 3=SoftR, 4=HardL, 5=HardR

// --- NEW LOGGING VARIABLES ---
int lastTipX = 160; 
int lastSlant = 0;              
const char* activeMode = "TIP"; 

// --- NEW: WI-FI RECONNECT TIMER ---
unsigned long lastWiFiTry = 0; 

void setup() {
    Serial.begin(115200);
    
    // --- MODE SELECTION SETUP ---
    if (useWiFi) {
        Serial.println("Starting Robot Hotspot...");
        WiFi.softAP(ap_ssid, ap_pass);
        Serial.print("Robot Hotspot Created! Robot IP is: ");
        Serial.println(WiFi.softAPIP()); 
        Serial.println("Wi-Fi network is active in the background.");
    } else {
        Serial.println("Wi-Fi OFF. Using USB Serial Cable for data.");
    }

    Wire.begin(21, 22);
    Wire.setTimeOut(100);

    pinMode(ENA, OUTPUT); pinMode(IN1, OUTPUT); pinMode(IN2, OUTPUT);
    pinMode(ENB, OUTPUT); pinMode(IN3, OUTPUT); pinMode(IN4, OUTPUT);
    stopMotors();

    delay(3000); 
    while (!huskylens.begin(Wire)) {
        Serial.println("TRAPPED: Cannot find HuskyLens!"); 
        delay(1000); 
    }
    Serial.println("Tank-Steer Hybrid System Ready!");
    Serial.println("--- DIAGNOSTICS STARTED ---");
}

void loop() {
    // --- NON-BLOCKING AUTO-RECONNECT (ONLY IF WIFI IS ON) ---
    if (useWiFi && !client.connected() && (millis() - lastWiFiTry > 2000)) {
        client.connect(hostIP, port);
        lastWiFiTry = millis(); 
    }

    // 1. READ JOYSTICK
    int joyX = analogRead(joyXPin);
    int joyY = analogRead(joyYPin);
    
    int mappedX = map(joyX, 0, 4095, 180, -180); 
    int mappedY = map(joyY, 0, 4095, -180, 180);

    // 2. CHECK FOR MANUAL OVERRIDE
    if (false) { // Joystick disabled
        int leftSpeed = constrain(mappedY + mappedX, -255, 255);
        int rightSpeed = constrain(mappedY - mappedX, -255, 255);
        setLeftMotor(leftSpeed);
        setRightMotor(rightSpeed);
        robotState = 0; 
    } 
    // 3. AUTO-MODE
    else {
        if (!huskylens.request()) {
            Serial.println("I2C ERROR - Hard Resetting Bus...");
            stopMotors();
            
            Wire.end(); delay(100); 
            Wire.begin(21, 22); delay(100);
            huskylens.begin(Wire); 
        } 
        
        else if (huskylens.available()) {
            while (huskylens.available()) {
                HUSKYLENSResult result = huskylens.read();
                if (result.command == COMMAND_RETURN_ARROW) {
                    
                    int tipX = result.xTarget;
                    int tipY = result.yTarget;
                    int tailX = result.xOrigin;
                    
                    lastTipX = tipX; 
                    lastDetectionTime = millis();
                    
                    // --- THE HYBRID LOOK-AHEAD STRATEGY ---
                    if (tipY < 60) { 
                        activeMode = "TIP"; 
                        lastSlant = 0;      
                        
                        if (tipX < 100) { robotState = 4; } 
                        else if (tipX >= 100 && tipX < 150) { robotState = 2; } 
                        else if (tipX > 170 && tipX <= 220) { robotState = 3; } 
                        else if (tipX > 220) { robotState = 5; } 
                        else { robotState = 1; } 
                    } 
                    else {
                        activeMode = "VEC"; 
                        int slant = tipX - tailX; 
                        lastSlant = slant;  
                        
                        if (tipX > 250) { robotState = 5; }
                        else if (tipX < 70) { robotState = 4; }
                        else if (slant < -40) { robotState = 4; } 
                        else if (slant >= -40 && slant < -15) { robotState = 2; } 
                        else if (slant > 15 && slant <= 40) { robotState = 3; } 
                        else if (slant > 40) { robotState = 5; } 
                        else { robotState = 1; } 
                    }
                }
            }
        }

        // 4. MOTOR EXECUTION 
        if (millis() - lastDetectionTime < MEMORY_TIMEOUT) {
            
            if (robotState == 4) { 
                setLeftMotor(autoHardRev); 
                setRightMotor(autoHardPush);
                Serial.printf("[%s] TipX: %3d | Slant: %4d | HARD L | L: %4d | R: %4d\n", activeMode, lastTipX, lastSlant, autoHardRev, autoHardPush);
            } 
            else if (robotState == 2) { 
                setLeftMotor(autoSoftInner); 
                setRightMotor(autoSoftOuter);
                Serial.printf("[%s] TipX: %3d | Slant: %4d | SOFT L | L: %4d | R: %4d\n", activeMode, lastTipX, lastSlant, autoSoftInner, autoSoftOuter);
            } 
            else if (robotState == 3) { 
                setLeftMotor(autoSoftOuter);
                setRightMotor(autoSoftInner);
                Serial.printf("[%s] TipX: %3d | Slant: %4d | SOFT R | L: %4d | R: %4d\n", activeMode, lastTipX, lastSlant, autoSoftOuter, autoSoftInner);
            } 
            else if (robotState == 5) { 
                setLeftMotor(autoHardPush);
                setRightMotor(autoHardRev);
                Serial.printf("[%s] TipX: %3d | Slant: %4d | HARD R | L: %4d | R: %4d\n", activeMode, lastTipX, lastSlant, autoHardPush, autoHardRev);
            } 
            else if (robotState == 1) { 
                setLeftMotor(autoBaseSpeed);
                setRightMotor(autoBaseSpeed);
                Serial.printf("[%s] TipX: %3d | Slant: %4d | STRT   | L: %4d | R: %4d\n", activeMode, lastTipX, lastSlant, autoBaseSpeed, autoBaseSpeed);
            }
            
            // --- DEAD RECKONING ODOMETRY ---
            if (robotState == 1) { 
                posX += cos(heading) * 1.0;  
                posY += sin(heading) * 1.0; 
            } 
            else if (robotState == 2) { 
                heading += 0.002;            
                posX += cos(heading) * 0.8; 
                posY += sin(heading) * 0.8; 
            } 
            else if (robotState == 3) { 
                heading -= 0.002; 
                posX += cos(heading) * 0.8; 
                posY += sin(heading) * 0.8; 
            } 
            else if (robotState == 4) { 
                heading += 0.0075;             
            } 
            else if (robotState == 5) { 
                heading -= 0.0075; 
            }

            // ==========================================
            // --- MANUAL DATA ROUTING ---
            // ==========================================
            if (useWiFi) {
                // Send over Wi-Fi
                if (client.connected()) {
                    client.print("DATA:");
                    client.print(posX);
                    client.print(",");
                    client.println(posY);
                }
            } else {
                // Send over USB Cable
                Serial.print("DATA:");
                Serial.print(posX);
                Serial.print(",");
                Serial.println(posY);
            }
            // ==========================================
            
        } else {
            stopMotors();
            robotState = 0; 
            Serial.println("!!! CAMERA LOST LINE - MOTORS STOPPED !!!");
        }
    }
    delay(20); 
}

// --- UNIVERSAL MOTOR FUNCTIONS ---
void setLeftMotor(int speed) {
    if (speed > 0) {
        digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW); analogWrite(ENA, speed);
    } else if (speed < 0) {
        digitalWrite(IN1, LOW); digitalWrite(IN2, HIGH); analogWrite(ENA, abs(speed));
    } else {
        digitalWrite(IN1, LOW); digitalWrite(IN2, LOW); analogWrite(ENA, 0);
    }
}

void setRightMotor(int speed) {
    if (speed > 0) {
        digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW); analogWrite(ENB, speed);
    } else if (speed < 0) {
        digitalWrite(IN3, LOW); digitalWrite(IN4, HIGH); analogWrite(ENB, abs(speed));
    } else {
        digitalWrite(IN3, LOW); digitalWrite(IN4, LOW); analogWrite(ENB, 0);
    }
}

void stopMotors() {
    setLeftMotor(0); setRightMotor(0);
}
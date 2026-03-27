#include "HUSKYLENS.h"
#include "Wire.h"

HUSKYLENS huskylens;

// --- Motor Wiring ---
int ENA = 32; int IN1 = 33; int IN2 = 25; 
int ENB = 14; int IN3 = 26; int IN4 = 27; 

// --- Joystick Pins ---
int joyXPin = 35; 
int joyYPin = 34; 

// --- TANK STEERING SETTINGS ---
int autoBaseSpeed = 130;  // Speed for straightaways
int autoTurnSpeed = -100; // NEGATIVE means the inner wheel spins BACKWARDS for a tight pivot!

// --- Odometry Variables ---
float posX = 0.0, posY = 0.0, heading = 1.5708;
float moveDistance = 2.0; 

void setup() {
    Serial.begin(115200);
    Wire.begin(21, 22);

    pinMode(ENA, OUTPUT); pinMode(IN1, OUTPUT); pinMode(IN2, OUTPUT);
    pinMode(ENB, OUTPUT); pinMode(IN3, OUTPUT); pinMode(IN4, OUTPUT);
    stopMotors();

    delay(3000); 
    while (!huskylens.begin(Wire)) {
        Serial.println("TRAPPED: Cannot find HuskyLens!"); 
        delay(1000); 
    }
    Serial.println("Tank-Steer Hybrid System Ready!");
}

void loop() {
    // 1. READ JOYSTICK
    int joyX = analogRead(joyXPin);
    int joyY = analogRead(joyYPin);
    
    // Map X and Y (Adjusted for your specific joystick orientation)
    int mappedX = map(joyX, 0, 4095, 180, -180); 
    int mappedY = map(joyY, 0, 4095, -180, 180);

    // 2. CHECK FOR MANUAL OVERRIDE (Deadzone of 100)
    if (abs(mappedX) > 100 || abs(mappedY) > 100) {
        int leftSpeed = constrain(mappedY + mappedX, -255, 255);
        int rightSpeed = constrain(mappedY - mappedX, -255, 255);
        setLeftMotor(leftSpeed);
        setRightMotor(rightSpeed);
    } 
    // 3. AUTO-MODE: TANK STEER LINE FOLLOWING
    else {
        if (!huskylens.request()) {
            Serial.println("I2C ERROR - Restarting...");
            stopMotors();
            Wire.end(); delay(100); Wire.begin(21, 22); delay(100);
        } 
        else if (huskylens.available()) {
            while (huskylens.available()) {
                HUSKYLENSResult result = huskylens.read();
                if (result.command == COMMAND_RETURN_ARROW) {
                    int tipX = result.xTarget;
                    
                    if (tipX < 140) { 
                        // TANK TURN LEFT: Right wheel FWD, Left wheel REV
                        setLeftMotor(autoTurnSpeed); 
                        setRightMotor(autoBaseSpeed);
                        heading += 0.25; // Sharp turn = faster heading change
                    } 
                    else if (tipX > 180) { 
                        // TANK TURN RIGHT: Left wheel FWD, Right wheel REV
                        setLeftMotor(autoBaseSpeed);
                        setRightMotor(autoTurnSpeed);
                        heading -= 0.25;
                    } 
                    else { 
                        // STRAIGHT: Both wheels FWD
                        setLeftMotor(autoBaseSpeed);
                        setRightMotor(autoBaseSpeed);
                        posX += cos(heading) * moveDistance;
                        posY += sin(heading) * moveDistance;
                    }
                    Serial.print(posX); Serial.print(","); Serial.println(posY);
                }
            }
        } else {
            stopMotors(); 
        }
    }
    delay(20); 
}

// --- UNIVERSAL MOTOR FUNCTIONS (Supports Reverse) ---
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
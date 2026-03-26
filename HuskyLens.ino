#include "HUSKYLENS.h"
#include "Wire.h"

HUSKYLENS huskylens;

// --- Motor Wiring (Left: 1/2, Right: 3/4) ---
int ENA = 32; int IN1 = 33; int IN2 = 25; 
int ENB = 14; int IN3 = 26; int IN4 = 27; 

int baseSpeed = 120;  
int turnSpeed = 100;  

// --- ODOMETRY (Mapping) VARIABLES ---
float posX = 0.0;
float posY = 0.0;
float heading = 1.5708; // 90 degrees in radians (facing straight "up")

// "Fake" distance units
float moveDistance = 2.0; 
float turnAngle = 0.15;   

void setup() {
    Serial.begin(115200);
    Wire.begin(21, 22);

    pinMode(ENA, OUTPUT); pinMode(IN1, OUTPUT); pinMode(IN2, OUTPUT);
    pinMode(ENB, OUTPUT); pinMode(IN3, OUTPUT); pinMode(IN4, OUTPUT);
    stopMotors();

    while (!huskylens.begin(Wire)) {
        delay(1000); // Muted so it doesn't break Processing!
    }
}

void loop() {
    if (!huskylens.request() || !huskylens.available()) {
        stopMotors();
    } 
    else {
        while (huskylens.available()) {
            HUSKYLENSResult result = huskylens.read();
            
            if (result.command == COMMAND_RETURN_ARROW) {
                int targetX = result.xTarget;

                if (targetX < 130) {
                    turnLeft();
                } 
                else if (targetX > 190) {
                    turnRight();
                } 
                else {
                    driveForward();
                }
                
                // --- SEND MATH TO COMPUTER ---
                // This replaces the English sentences!
                Serial.print(posX);
                Serial.print(",");
                Serial.println(posY);
            } 
            else {
                stopMotors();
            }
        }
    }
    delay(20); 
}

// --- MOTOR & MAPPING FUNCTIONS ---

void driveForward() {
    digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW); analogWrite(ENA, baseSpeed);
    digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW); analogWrite(ENB, baseSpeed);
    
    posX += cos(heading) * moveDistance;
    posY += sin(heading) * moveDistance;
}

void turnLeft() {
    digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW); analogWrite(ENB, turnSpeed);
    digitalWrite(IN1, LOW); digitalWrite(IN2, HIGH); analogWrite(ENA, turnSpeed);
    
    heading += turnAngle;
    posX += cos(heading) * (moveDistance * 0.2); 
    posY += sin(heading) * (moveDistance * 0.2);
}

void turnRight() {
    digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW); analogWrite(ENA, turnSpeed);
    digitalWrite(IN3, LOW); digitalWrite(IN4, HIGH); analogWrite(ENB, turnSpeed);
    
    heading -= turnAngle;
    posX += cos(heading) * (moveDistance * 0.2); 
    posY += sin(heading) * (moveDistance * 0.2);
}

void stopMotors() {
    analogWrite(ENA, 0); analogWrite(ENB, 0);
    digitalWrite(IN1, LOW); digitalWrite(IN2, LOW);
    digitalWrite(IN3, LOW); digitalWrite(IN4, LOW);
}
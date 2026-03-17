#include <ESP32Servo.h>

Servo droneMotor;
const int escPin = 13;

const int enA = 32; const int in1 = 33; const int in2 = 25;
const int enB = 26; const int in3 = 27; const int in4 = 14;

int power = 1000; 

void setup() {
  Serial.begin(115200);
  
  pinMode(enA, OUTPUT); pinMode(in1, OUTPUT); pinMode(in2, OUTPUT);
  pinMode(enB, OUTPUT); pinMode(in3, OUTPUT); pinMode(in4, OUTPUT);
  
  droneMotor.attach(escPin, 1000, 2000);
  stopAll(); // Start all stopped
  
  Serial.println("System Arming. Wait 3s");
  delay(3000);
  Serial.println("Commands: 'G' = Go Faster, 'S' = EMERGENCY STOP");
}

void loop() {
  if (Serial.available() > 0) {
    char cmd = Serial.read();

    if (cmd == 'g' || cmd == 'G') {
      power = constrain(power + 100, 1000, 2000);
      updateMotors();
    } 
    else if (cmd == 's' || cmd == 'S') {
      stopAll();
      Serial.println("Emergency Stop");
    }
  }
}

void updateMotors() {
  droneMotor.writeMicroseconds(power);
  
  int wheelSpeed = map(power, 1000, 2000, 0, 255);
  digitalWrite(in1, HIGH); digitalWrite(in2, LOW);
  digitalWrite(in3, HIGH); digitalWrite(in4, LOW);
  analogWrite(enA, wheelSpeed);
  analogWrite(enB, wheelSpeed);
  
  Serial.print("Current Signal: "); Serial.println(power);
}

void stopAll() {
  power = 1000;
  droneMotor.writeMicroseconds(1000); // Send stop signal to ESC
  
  // Cut power to wheels
  digitalWrite(in1, LOW); digitalWrite(in2, LOW);
  digitalWrite(in3, LOW); digitalWrite(in4, LOW);
  analogWrite(enA, 0);
  analogWrite(enB, 0);
}
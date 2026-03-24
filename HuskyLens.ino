#include "HUSKYLENS.h"
#include "Wire.h"

HUSKYLENS huskylens;

void setup() {
    Serial.begin(115200);
    
    // Using the pin configuration that just worked for you!
    Wire.begin(21, 22); 

    Serial.println("Starting HuskyLens...");

    while (!huskylens.begin(Wire)) {
        Serial.println("Error: Connection lost. Check wires!");
        delay(2000);
    }
    
    Serial.println("HuskyLens Connected & Ready!");
}

void loop() {
    if (!huskylens.request()) {
        Serial.println("Failed to request data from HuskyLens.");
    } else if (!huskylens.available()) {
        // Uncomment the line below if you want to know when it sees nothing
        // Serial.println("Nothing in view..."); 
    } else {
        // Read the data when it sees an object
        while (huskylens.available()) {
            HUSKYLENSResult result = huskylens.read();
            
            if (result.command == COMMAND_RETURN_BLOCK) {
                Serial.print("Target Locked! ID: "); 
                Serial.print(result.ID);
                Serial.print(" | X: "); 
                Serial.print(result.xCenter);
                Serial.print(" | Y: "); 
                Serial.println(result.yCenter);
            }
        }
    }
    delay(100); // 100ms delay to keep the Serial Monitor readable
}
import processing.serial.*;

Serial myPort;
float robotX = 400; 
float robotY = 400;
float lastX = 400;
float lastY = 400;

void setup() {
  size(800, 800); 
  background(30); 
  
  // 1. PRINT ALL AVAILABLE PORTS
  println("AVAILABLE PORTS:");
  printArray(Serial.list());
  println("-------------------------");
  
  // 2. CONNECT TO THE PORT
  // Look at the black console box at the bottom of Processing.
  // Find your ESP32 port (e.g., "COM5") and type it EXACTLY here:
  String portName = "COM7"; 
  
  try {
    myPort = new Serial(this, portName, 115200); 
    myPort.bufferUntil('\n'); 
    println("Successfully connected to " + portName + "! Waiting for robot...");
  } catch (Exception e) {
    println("ERROR: Could not connect to " + portName + ". Is it typed correctly? Is Arduino Serial Monitor closed?");
  }
}

void draw() {
  stroke(255, 50, 50); 
  strokeWeight(4);     
  line(lastX, lastY, robotX, robotY);
  
  lastX = robotX;
  lastY = robotY;
}

void serialEvent(Serial myPort) {
  String inString = myPort.readStringUntil('\n');
  
  if (inString != null) {
    inString = trim(inString); 
    println("Robot says: " + inString); // This prints the raw math so we know it's working!
    
    String[] coords = split(inString, ','); 
    
    if (coords.length == 2) {
      float espX = float(coords[0]);
      float espY = float(coords[1]);
      
      robotX = 400 + espX;
      robotY = 400 - espY; 
    }
  }
}

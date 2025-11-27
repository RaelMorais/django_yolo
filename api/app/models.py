from django.db import models
from django.utils import timezone

class User(models.Model):
    name = models.CharField(max_length=100)
    rfid = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name

class Environment(models.Model):
    detected_people = models.JSONField(default=list, blank=True)
    people_count = models.PositiveIntegerField(default=0)      
    has_presence = models.BooleanField(default=False)         
    temperature = models.FloatField(default=0.0)
    humidity = models.FloatField(default=0.0)
    last_rfid = models.CharField(max_length=50, blank=True)
    light_white = models.BooleanField(default=False)
    light_blue = models.BooleanField(default=False)
    light_green = models.BooleanField(default=False)
    light_red = models.BooleanField(default=False)
    last_update = models.DateTimeField(default=timezone.now)


    def update_presence(self, rfid, temperature, humidity, presence):
        self.last_rfid = rfid

        if presence:
            if rfid not in self.detected_people:
                self.detected_people.append(rfid)  
            self.people_count = len(self.detected_people)  
        else:
            if rfid in self.detected_people:
                self.detected_people.remove(rfid)  
            self.people_count = len(self.detected_people)

        self.has_presence = bool(self.people_count)

        self.temperature = temperature
        self.humidity = humidity

        self.last_update = timezone.now()

        self.save()
        return self

class Log(models.Model):
    event = models.CharField(max_length=255)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"[{self.created_at}] {self.event}"

class PlatformDefault:
    platform = "default"
    version = "1.0.0"
    
    def __init__(self):
        pass

    def get_platform(self):
        return self.platform

    def get_version(self):
        return self.version

    def get_live(self):
        print(f"Get Live Stream Platform: {self.platform}, Version: {self.version}")


    
    
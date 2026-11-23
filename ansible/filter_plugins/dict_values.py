class FilterModule:
    def filters(self):
        return {"dict_values": self.values}

    def values(self, dictionary):
        return dictionary.values()

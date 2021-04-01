#!/usr/bin/python


class FilterModule(object):
    def filters(self):
        return {"dict_values": self.values}

    def values(self, dictionary):
        return dictionary.values()

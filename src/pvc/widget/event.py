"""
Event Widgets

"""

import os
import time
import tempfile
import threading

import pyVmomi

__all__ = ['EventWidget', 'EventCollector']


class EventWidget(object):
    def __init__(self, agent, dialog, obj):
        """
        Event Widget

        Args:
            agent         (VConnector): A VConnector instance
            dialog     (dialog.Dialog): A Dialog instance
            obj    (vim.ManagedEntity): A Managed Entity

        """
        self.agent = agent
        self.dialog = dialog
        self.obj = obj
        self.display()

    def display(self):
        self.dialog.infobox(
            text='Retrieving information ...'
        )

        fd, path = tempfile.mkstemp(prefix='pvcevents-')

        # We need to create the destination file where events
        # will be appended to because we don't know exactly how long
        # the event history collector will take to put any new
        # data in the file, so the operation can take long enough
        # to create the file and dialog(1) needs a valid and
        # already existing file in order to display the widget
        with open(path, 'w'):
            pass

        collector = EventCollector(
            agent=self.agent,
            obj=self.obj,
            path=path
        )
        collector.start()

        # Give it some time before displaying the widget
        time.sleep(1)

        self.dialog.tailbox(
            filepath=path,
            title=self.obj.name
        )

        collector.signal_stop()
        collector.join(1)
        os.unlink(path)


class EventCollector(threading.Thread):
    def __init__(self, agent, obj, path):
        """
        Event Collector Thread

        Args:
            agent        (VConnector): A VConnector instance
            obj   (vim.ManagedEntity): A Managed Entity
            path                (str): Path where new events are appended to

        """
        super().__init__()
        self.daemon = True
        self.time_to_die = threading.Event()

        self.agent = agent
        self.obj = obj
        self.path = path
        self.last_event_key = 0

    def run(self):
        entity_filter_spec = pyVmomi.vim.event.EventFilterSpec.ByEntity(
            entity=self.obj,
            recursion=pyVmomi.vim.event.EventFilterSpec.RecursionOption.all
        )

        filter_spec = pyVmomi.vim.event.EventFilterSpec(
            disableFullMessage=False,
            entity=entity_filter_spec
        )

        collector = self.agent.si.content.eventManager.CreateCollectorForEvents(
            filter=filter_spec
        )

        while not self.time_to_die.is_set():
            latest_events = self.get_latest_events(collector)
            if latest_events:
                self.save_events(latest_events)
            time.sleep(1)

        collector.DestroyCollector()

    def signal_stop(self):
        """
        Signal the thread that it's time to die

        """
        self.time_to_die.set()

    def get_latest_events(self, collector):
        """
        Get latest events up to the last known event

        Args:
            collector (vim.event.EventHistoryCollector): A collector instance

        Returns:
            A list of the latest events

        """
        latest_events = []
        latest_page = collector.latestPage
        for e in latest_page:
            if e.key == self.last_event_key:
                break
            else:
                latest_events.append(e)

        # The last event is the one with the largest key
        self.last_event_key = max([e.key for e in latest_page])
        latest_events.sort(key=lambda x: x.key)

        return latest_events

    def save_events(self, events):
        """
        Append new events to a file

        Args:
            events (list): A list of vim.event.Event instances

        """
        with open(self.path, 'a') as f:
            for e in events:
                if e.userName:
                    f.write('[{}]: User {}: {}\n'.format(str(e.createdTime), e.userName, e.fullFormattedMessage))
                else:
                    f.write('[{}]: {}\n'.format(str(e.createdTime), e.fullFormattedMessage))

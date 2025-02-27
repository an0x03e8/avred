import logging
import time
from intervaltree import Interval, IntervalTree
from typing import List
from model.extensions import Scanner, PluginFileFormat
from model.model import Data
from copy import deepcopy

from utils import *

SIG_SIZE = 128
PRINT_DELAY_SECONDS = 1


class Reducer():
    def __init__(self, file: PluginFileFormat, scanner: Scanner):
        self.file: PluginFileFormat = file
        self.scanner = scanner

        self.lastPrintTime: int = 0
        self.chunks_tested: int = 0


    def scan(self, offsetStart, offsetEnd) -> List[Interval]:
        it = IntervalTree()
        data = self.file.Data()
        self._scanSection(data, offsetStart, offsetEnd, it)
        it.merge_overlaps(strict=False)
        return sorted(it)


    def _scanData(self, data: Data):
        newFileData: Data = self.file.getFileDataWith(data)
        return self.scanner.scannerDetectsBytes(newFileData.getBytes(), self.file.filename)


    # recursive
    def _scanSection(self, data: Data, sectionStart, sectionEnd, it):
        size = sectionEnd - sectionStart
        chunkSize = int(size // 2)
        self._printStatus()
        
        #logging.debug(f"Testing: {sectionStart}-{sectionEnd} with size {sectionEnd-sectionStart} (chunkSize {chunkSize} bytes)")
        #logging.debug(f"Testing Top: {sectionStart}-{sectionStart+chunkSize} (chunkSize {chunkSize} bytes)")
        #logging.debug(f"Testing Bot: {sectionStart+chunkSize}-{sectionStart+chunkSize+chunkSize} (chunkSize {chunkSize} bytes)")

        if chunkSize < 2:
            logging.debug(f"Very small chunksize for a signature, weird. Ignoring. {sectionStart}-{sectionEnd}")
            return

        dataChunkTopNull = deepcopy(data)
        dataChunkTopNull.patchDataFill(sectionStart, chunkSize)

        dataChunkBotNull = deepcopy(data)
        dataChunkBotNull.patchDataFill(sectionStart+chunkSize, chunkSize)

        detectTopNull = self._scanData(dataChunkTopNull)
        detectBotNull = self._scanData(dataChunkBotNull)

        if detectTopNull and detectBotNull:
            # Both halves are detected
            # Continue scanning both halves independantly, but with each other halve
            # zeroed out (instead of the complete file)
            #logging.debug("--> Both halves are detected!")
            
            self._scanSection(dataChunkBotNull, sectionStart, sectionStart+chunkSize, it)
            self._scanSection(dataChunkTopNull, sectionStart+chunkSize, sectionEnd, it)

        elif not detectTopNull and not detectBotNull:
            # both parts arent detected anymore

            if chunkSize < SIG_SIZE:
                # Small enough, no more detections
                #logging.debug("No more detection")
                dataBytes = data.getBytesRange(sectionStart, sectionStart+size)
                logging.info(f"Result: {sectionStart}-{sectionEnd} ({sectionEnd-sectionStart} bytes)" 
                             + "\n" + hexdmp(dataBytes, offset=sectionStart))
                it.add ( Interval(sectionStart, sectionStart+size) )
            else: 
                # make it smaller still. Take complete data (not nulled)
                #logging.debug("--> No detections anymore, but too big. Continue anyway...")
                self._scanSection(data, sectionStart, sectionStart+chunkSize, it)
                self._scanSection(data, sectionStart+chunkSize, sectionEnd, it)

            #print("TopNull:")
            #data = chunkBotNull[sectionStart:sectionStart+chunkSize]
            #print(hexdump.hexdump(data, result='return'))

            #print("BotNull:")
            #data = chunkTopNull[sectionStart+chunkSize:sectionStart+chunkSize+chunkSize]
            #print(hexdump.hexdump(data, result='return'))

        elif not detectTopNull:
            # Detection in the top half
            logging.debug("--> Do Top")
            self._scanSection(data, sectionStart, sectionStart+chunkSize, it)
        elif not detectBotNull:
            # Detection in the bottom half
            logging.debug("--> Do Bot")
            self._scanSection(data, sectionStart+chunkSize, sectionEnd, it)

        return


    def _printStatus(self):
        self.chunks_tested += 1

        currentTime = time.time()
        if currentTime > self.lastPrintTime + PRINT_DELAY_SECONDS:
            self.lastPrintTime = currentTime
            logging.info("Reducing: {} chunks done".format(self.chunks_tested))

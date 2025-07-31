This tool uses pytrends, an unofficial Google Trends API, to gather data on how often people are searching particular phrases.
The idea is that this would form part of a dashboard that would let someone make an informed decision on what items they should try to resell.

Currently (31/07) this app has the ability to:

-Add and delete phrases from a google sheet 
  
-create a table of all phrases in the sheet, signalling spikes/drops in interest, and whether those changes are currently sustained
  
-graph the phrases with the biggest changes and highest levels of interest
  
-graph any phrase in the list upon request (which can be compared with other phrases - up to 5 in one graph)


Pytrends has some limitations - only being able to graph 5 phrases at a time, and the possiblility of being rate limited if calling for phrase trend data too often.
I have tried to prevent rate limiting by setting a time delay of 5 seconds between batches of phrases (5 at a time), however there may be some more stuff that can be done.
The current paramaters regarding what constitutes a spike/drop and whether it is sustained can be played around with, as well as the size of the time periods being used, depending on how sensitive you want it to be.
There's a lot of room for expansion/improvement - flashier alerts for big movements in interest, more data analysis on volatility, stopping the addition/deletion of phrases from refreshing the page etc.

I have explained how Google Trends works within the code and interface as shown below:

-Google Trends uses values from 0-100 for the number of searches including a particular phrase
  
-These values are relative to a phrases' peak interest (set at 100)
  
-When graphed, the amount of interest in each phrase is then compared at an absolute level
  
-It is unfortunately not possible to get absolute figures without comparison

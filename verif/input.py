import csv
import datetime
import numpy as np
import os
import re
import time
try:
   from netCDF4 import Dataset as netcdf
except:
   from scipy.io.netcdf import netcdf_file as netcdf

import verif.location
import verif.util
import verif.variable
import verif.field


def get_input(filename):
   if not os.path.isfile(filename):
      verif.util.error("File '" + filename + "' does not exist")
   is_nc = verif.util.is_valid_nc(filename)
   if is_nc:
      if(verif.input.Netcdf.is_valid(filename)):
         input = verif.input.Netcdf(filename)
      elif(verif.input.Comps.is_valid(filename)):
         input = verif.input.Comps(filename)
      else:
         verif.util.error("File '" + filename + "' does not have the correct Netcdf format")
   elif(verif.input.Text.is_valid(filename)):
      input = verif.input.Text(filename)
   else:
      verif.util.error("File '" + filename + "' is not a valid input file")
   return input


class Input(object):
   """ Base class representing verification data

   Stores observation and forecast data in deterministic, ensemble, and
   probabilistic format.

   Class attributes:
      description: A string description of the parser

   Attributes:
      name: A string name identifying the dataset (such as a filename)
      fullname: A string name identifying the dataset (such as a filename)
      shortname: A string name identifying the dataset (such as a filename)
      variable: A verif.variable representing the stored in the input

      times (np.array): Available initialization times (unix time)
      leadtimes (np.array): Available leadtimes (in hours)
      locations (list): A list of verif.location of available locations
      thresholds (np.array): Available thresholds
      quantiles (np.array): Available quantiles

      The following are 3D numpy arrays with dims (time, leadtime, location). These are None if not
      present.
      obs: Observations
      fcst: Forecasts
      pit: Verifying probability integral transform values (i.e. the CDF where
         the observation falls in)

      ensemble: A 4D numpy array of ensemble data with dims (time,leadtime,location,member)
      threshold_scores: A 4D numpy array with CDF values for each threshold
         with dims (time,leadtime,location, threshold)
      quantile_scores: A 4D numpy array with values at certain quantiles with
         dims (time,leadtime,location, quantile)

   Subclasses must populate all attributes
   """
   description = None  # Overwrite this

   def get_fields(self):
      """ Get the available fields in this input

      Returns:
         list(verif.field): The available fields
      """
      fields = list()
      if self.obs is not None:
         fields.append(verif.field.Obs())
      if self.fcst is not None:
         fields.append(verif.field.Fcst())
      if self.pit is not None:
         fields.append(verif.field.Pit())
      thresholds = [verif.field.Threshold(threshold) for threshold in self.thresholds]
      quantiles = [verif.field.Quantile(quantile) for quantile in self.quantiles]
      return fields + thresholds + quantiles

   @property
   def name(self):
      """ Default to setting the name to the filename without the path """
      I = self.fullname.rfind('/')
      name = self.fullname[I + 1:]
      return name

   @property
   def shortname(self):
      """ Default to setting the name to the filename without the path and extension"""
      I = self.name.rfind('.')
      name = self.name[:I]
      return name


class Netcdf(Input):
   """
   Netcdf file format
   """
   description = "NetCDF format that runs much quicker than the text format, though requires more effort to create. See https://github.com/WFRT/verif for more information about creating this file."

   def __init__(self, filename):
      self.fullname = filename
      self._filename = os.path.expanduser(filename)
      self._file = netcdf(self._filename, 'r')
      self.times = self._get_times()
      self.leadtimes = self._get_leadtimes()
      self.locations = self._get_locations()
      self.thresholds = self._get_thresholds()
      self.quantiles = self._get_quantiles()
      self.variable = self._get_variable()

   @staticmethod
   def is_valid(filename):
      # First check if the file is a valid Netcdf file
      try:
         file = netcdf(filename, 'r')
         valid = True

         # Check required dimensions
         dims = [dim for dim in file.dimensions]
         required_dims = ["time", "location", "leadtime"]
         for required_dim in required_dims:
            valid = valid and required_dim in dims

         # Check required variables
         required_vars = ["time", "location", "leadtime"]
         vars = [var for var in file.variables]
         for required_var in required_vars:
            valid = valid and required_var in vars

         file.close()
         return valid
      except:
         return False

   @property
   def obs(self):
      if "obs" in self._file.variables:
         return verif.util.clean(self._file.variables["obs"])
      else:
         return None

   @property
   def fcst(self):
      if "fcst" in self._file.variables:
         return verif.util.clean(self._file.variables["fcst"])
      else:
         return None

   @property
   def pit(self):
      if "pit" in self._file.variables:
         return verif.util.clean(self._file.variables["pit"])
      else:
         return None

   @property
   def ensemble(self):
      if "ensemble" in self._file.variables:
         return verif.util.clean(self._file.variables["ens"])
      else:
         return None

   @property
   def threshold_scores(self):
      if "cdf" in self._file.variables:
         return verif.util.clean(self._file.variables["cdf"])
      else:
         return None

   @property
   def quantile_scores(self):
      if "x" in self._file.variables:
         return verif.util.clean(self._file.variables["x"])
      else:
         return None

   def _get_times(self):
      return verif.util.clean(self._file.variables["time"])

   def _get_locations(self):
      lat = verif.util.clean(self._file.variables["lat"])
      lon = verif.util.clean(self._file.variables["lon"])
      id = verif.util.clean(self._file.variables["location"])
      elev = verif.util.clean(self._file.variables["altitude"])
      locations = list()
      for i in range(0, lat.shape[0]):
         location = verif.location.Location(id[i], lat[i], lon[i], elev[i])
         locations.append(location)
      return locations

   def _get_leadtimes(self):
      return verif.util.clean(self._file.variables["leadtime"])

   def _get_thresholds(self):
      if "threshold" in self._file.variables:
         return verif.util.clean(self._file.variables["threshold"])
      else:
         return np.array([])

   def _get_quantiles(self):
      if "quantile" in self._file.variables:
         return verif.util.clean(self._file.variables["quantile"])
      else:
         return np.array([])

   def _get_variable(self):
      if hasattr(self._file, "long_name"):
         name = self._file.long_name
      elif hasattr(self._file, "standard_name"):
         name = self._file.standard_name
      else:
         name = "Unknown variable"

      units = ""
      if hasattr(self._file, "units"):
         units = self._file.units

      if units == "":
         units = "Unknown units"
      elif units == "%":
         units = "%"
      else:
         # Wrap units in $$ so that the latex interpreter can be used when
         # displaying units
         units = "$" + units + "$"

      x0 = verif.variable.guess_x0(name)
      x1 = verif.variable.guess_x1(name)
      return verif.variable.Variable(name, units, x0=x0, x1=x1)


# Flat text file format
class Text(Input):
   description = "Data organized in rows and columns with space as a delimiter. Each row represents one forecast/obs pair, and each column represents one attribute of the data. Here is an example:"\
   "\n"\
   "# variable: Temperature\n"\
   "# units: $^oC$\n"\
   "date     leadtime location lat     lon      altitude  obs  fcst  p10\n"\
   "20150101 0        214       49.2    -122.1   92       3.4      2.1    0.914 -1.9\n"
   "20150101 1        214       49.2    -122.1   92       4.7      4.2    0.858 0.1\n"
   "20150101 0        180       50.3    -120.3   150      0.2      -1.2   0.992 -2.1\n"
   "\n"\
   "Any lines starting with '#' can be metadata (currently variable: and units: are recognized). After that is a header line that must describe the data columns below. The following attributes are recognized: date (in YYYYMMDD) or unixtime (in seconds since 1970-01-01 00:00:00 +00:00), leadtime (in hours), location (location identifier), lat (in degrees), lon (in degrees), obs (observations), fcst (deterministic forecast), p<number> (cumulative probability at a threshold of for example 10), and q<number> (value corresponding to the <number> quantile, e.g. q0.9 for the 90th precentile). obs and fcst are required columns: a value of 0 is used for any missing column. The columns can be in any order. If 'id' is not provided, then they are assigned sequentially starting at 0. If there is conflicting information (for example different lat/lon/altitude for the same id), then the information from the first row containing id will be used. For compatibility reasons, 'offset' can be used instead of 'leadtime', 'id' instead of 'location', and 'elev' instead of 'altitude'."

   def __init__(self, filename):
      self.fullname = filename
      self._filename = os.path.expanduser(filename)
      file = open(self._filename, 'rU')
      self._variable_units = "Unknown units"
      self._variable_name = "Unknown variable"

      self._times = set()
      self._leadtimes = set()
      self._locations = set()
      self._quantiles = set()
      self._thresholds = set()
      self.obs = None
      self.fcst = None
      self.pit = None
      fields = dict()
      obs = dict()
      fcst = dict()
      cdf = dict()
      pit = dict()
      x = dict()
      indices = dict()
      header = None

      # Default values if columns not available
      leadtime = 0
      time = 0
      lat = 0
      lon = 0
      elev = 0
      # Store location data, to ensure we don't have conflicting lat/lon/elev info for the same ids
      locationInfo = dict()
      shownConflictingWarning = False

      import time
      start = time.time()
      # Read the data into dictionary with (time,leadtime,lat,lon,elev) as key and obs/fcst as values
      for rowstr in file:
         if(rowstr[0] == "#"):
            curr = rowstr[1:]
            curr = curr.split()
            if(curr[0] == "variable:"):
               self._variable_name = ' '.join(curr[1:])
            elif(curr[0] == "units:"):
               self._variable_units = curr[1]
            else:
               verif.util.warning("Ignoring line '" + rowstr.strip() + "' in file '" + self._filename + "'")
         else:
            row = rowstr.split()
            if(header is None):
               # Parse the header so we know what each column represents
               header = row
               for i in range(0, len(header)):
                  att = header[i]
                  if(att == "offset"):
                     indices["leadtime"] = i
                  else:
                     indices[att] = i
            else:
               if(len(row) is not len(header)):
                  verif.util.error("Incorrect number of columns (expecting %d) in row '%s'"
                        % (len(header), rowstr.strip()))
               if("date" in indices):
                  date = int(self._clean(row[indices["date"]]))
                  time = verif.util.date_to_unixtime(date)
                  add = 0
                  if("time" in indices):
                     add = (self._clean(row[indices["time"]]))*3600
                  time = time + add
               elif("unixtime" in indices):
                  time = self._clean(row[indices["unixtime"]])
               self._times.add(time)
               if("leadtime" in indices):
                  leadtime = self._clean(row[indices["leadtime"]])
               self._leadtimes.add(leadtime)
               if("location" in indices):
                  id = self._clean(row[indices["location"]])
               elif("id" in indices):
                  id = self._clean(row[indices["id"]])
               else:
                  id = np.nan

               # Lookup previous locationInfo
               currLat = np.nan
               currLon = np.nan
               currElev = np.nan
               if("lat" in indices):
                  currLat = self._clean(row[indices["lat"]])
               if("lon" in indices):
                  currLon = self._clean(row[indices["lon"]])
               if("altitude" in indices):
                  currElev = self._clean(row[indices["altitude"]])
               elif("elev" in indices):
                  currElev = self._clean(row[indices["elev"]])

               if not np.isnan(id) and id in locationInfo:
                  lat = locationInfo[id].lat
                  lon = locationInfo[id].lon
                  elev = locationInfo[id].elev
                  if not shownConflictingWarning:
                     if (not np.isnan(currLat) and abs(currLat - lat) > 0.0001) or (not np.isnan(currLon) and abs(currLon - lon) > 0.0001) or (not np.isnan(currElev) and abs(currElev - elev) > 0.001):
                        print currLat - lat, currLon - lon, currElev - elev
                        verif.util.warning("Conflicting lat/lon/elev information: (%f,%f,%f) does not match (%f,%f,%f)" % (currLat, currLon, currElev, lat, lon, elev))
                        shownConflictingWarning = True
               else:
                  if np.isnan(currLat):
                     currLat = 0
                  if np.isnan(currLon):
                     currLon = 0
                  if np.isnan(currElev):
                     currElev = 0
                  location = verif.location.Location(id, currLat, currLon, currElev)
                  self._locations.add(location)
                  locationInfo[id] = location

               lat = locationInfo[id].lat
               lon = locationInfo[id].lon
               elev = locationInfo[id].elev
               key = (time, leadtime, id, lat, lon, elev)
               if "obs" in indices:
                  obs[key] = self._clean(row[indices["obs"]])
               if "fcst" in indices:
                  fcst[key] = self._clean(row[indices["fcst"]])
               quantileFields = self._get_quantile_fields(header)
               thresholdFields = self._get_threshold_fields(header)
               if "pit" in indices:
                  pit[key] = self._clean(row[indices["pit"]])
               for field in quantileFields:
                  quantile = float(field[1:])
                  self._quantiles.add(quantile)
                  key = (time, leadtime, id, lat, lon, elev, quantile)
                  x[key] = self._clean(row[indices[field]])
               for field in thresholdFields:
                  threshold = float(field[1:])
                  self._thresholds.add(threshold)
                  key = (time, leadtime, id, lat, lon, elev, threshold)
                  cdf[key] = self._clean(row[indices[field]])

      file.close()
      self._times = list(self._times)
      self._leadtimes = list(self._leadtimes)
      self._locations = list(self._locations)
      self._quantiles = list(self._quantiles)
      self._thresholds = list(self._thresholds)
      Ntimes = len(self._times)
      Nleadtimes = len(self._leadtimes)
      Nlocations = len(self._locations)
      Nquantiles = len(self._quantiles)
      Nthresholds = len(self._thresholds)

      # Put the dictionary data into a regular 3D array
      if len(obs) > 0:
         self.obs = np.zeros([Ntimes, Nleadtimes, Nlocations], 'float') * np.nan
      if len(fcst) > 0:
         self.fcst = np.zeros([Ntimes, Nleadtimes, Nlocations], 'float') * np.nan
      if len(pit) > 0:
         self.pit = np.zeros([Ntimes, Nleadtimes, Nlocations], 'float') * np.nan
      self.threshold_scores = np.zeros([Ntimes, Nleadtimes, Nlocations, Nthresholds], 'float') * np.nan
      self.quantile_scores = np.zeros([Ntimes, Nleadtimes, Nlocations, Nquantiles], 'float') * np.nan
      for d in range(0, Ntimes):
         time = self._times[d]
         for o in range(0, len(self._leadtimes)):
            leadtime = self._leadtimes[o]
            for s in range(0, len(self._locations)):
               location = self._locations[s]
               id = location.id
               lat = location.lat
               lon = location.lon
               elev = location.elev
               key = (time, leadtime, id, lat, lon, elev)
               if(key in obs):
                  self.obs[d][o][s] = obs[key]
               if(key in fcst):
                  self.fcst[d][o][s] = fcst[key]
               if(key in pit):
                  self.pit[d][o][s] = pit[key]
               for q in range(0, len(self._quantiles)):
                  quantile = self._quantiles[q]
                  key = (time, leadtime, id, lat, lon, elev, quantile)
                  if(key in x):
                     self.quantile_scores[d, o, s, q] = x[key]
               for t in range(0, len(self._thresholds)):
                  threshold = self._thresholds[t]
                  key = (time, leadtime, id, lat, lon, elev, threshold)
                  if(key in cdf):
                     self.threshold_scores[d, o, s, t] = cdf[key]
      maxLocationId = np.nan
      for location in self._locations:
         if(np.isnan(maxLocationId)):
            maxLocationId = location.id
         elif(location.id > maxLocationId):
            maxLocationId = location.id

      counter = 0
      if(not np.isnan(maxLocationId)):
         counter = maxLocationId + 1

      for location in self._locations:
         if(np.isnan(location.id)):
            location.id = counter
            counter = counter + 1

      self.times = np.array(self._times)
      self.leadtimes = np.array(self._leadtimes)
      self.thresholds = np.array(self._thresholds)
      self.quantiles = np.array(self._quantiles)
      self.locations = self._locations
      self.variable = self._get_variable()

   @staticmethod
   def is_valid(filename):
      return os.path.isfile(filename)

   def _get_variable(self):
      x0 = verif.variable.guess_x0(self._variable_name)
      x1 = verif.variable.guess_x1(self._variable_name)
      return verif.variable.Variable(self._variable_name, self._variable_units, x0=x0, x1=x1)

   # Parse string into float, changing -999 into np.nan
   def _clean(self, value):
      fvalue = float(value)
      if(fvalue == -999):
         fvalue = np.nan
      return fvalue

   def _get_quantile_fields(self, fields):
      quantiles = list()
      for att in fields:
         if(att[0] == "q"):
            quantiles.append(att)
      return quantiles

   def _get_threshold_fields(self, fields):
      thresholds = list()
      for att in fields:
         if(att[0] == "p" and att != "pit"):
            thresholds.append(att)
      return thresholds


class Comps(Input):
   """
   Original NetCDF file format used by OutputVerif in COMPS (https://github.com/WFRT/Comps)
   """
   _dimensionNames = ["Date", "Offset", "Location", "Lat", "Lon", "Elev"]
   description = "Undocumented legacy NetCDF format, to be phased out."

   def __init__(self, filename):
      self.fullname = filename
      self._filename = os.path.expanduser(filename)
      self._file = netcdf(self._filename, 'r')

      # Pre-load these variables, to save time when queried repeatedly
      dates = verif.util.clean(self._file.variables["Date"])
      self.times = np.array([verif.util.date_to_unixtime(int(date)) for date in dates], int)
      self.leadtimes = verif.util.clean(self._file.variables["Offset"])
      self.thresholds = self._get_thresholds()
      self.quantiles = self._get_quantiles()
      self.locations = self._get_locations()
      self.variable = self._get_variable()

   @staticmethod
   def is_valid(filename):
      """ Checks that 'filename' is a valid object of this type """
      valid = True
      try:
         file = netcdf(filename, 'r')
         required_dimensions = ["Offset", "Date", "Location"]
         for dim in required_dimensions:
            valid = valid & (dim in file.dimensions)
         file.close()
         return valid
      except:
         return False

   @property
   def obs(self):
      if "obs" in self._file.variables:
         return verif.util.clean(self._file.variables["obs"])
      else:
         return None

   @property
   def fcst(self):
      if "obs" in self._file.variables:
         return verif.util.clean(self._file.variables["fcst"])
      else:
         return None

   @property
   def pit(self):
      if "pit" in self._file.variables:
         return verif.util.clean(self._file.variables["pit"])
      else:
         return None

   @property
   def threshold_scores(self):
      thresholds = self.thresholds
      Nt = len(thresholds)
      values = None

      for t in range(0, Nt):
         p_var = self._verif_to_comps_threshold(thresholds[t])
         np.array([Nt], float)
         temp = self._get_score(p_var)
         if values is None:
            shape = [i for i in temp.shape] + [Nt]
            values = np.zeros(shape, float)
         values[:, :, :, t] = temp

      return values

   @property
   def quantile_scores(self):
      quantiles = self.quantiles
      Nq = len(quantiles)
      values = None

      for q in range(0, Nq):
         q_var = self._verif_to_comps_quantile(quantiles[q])
         np.array([Nq], float)
         temp = self._get_score(q_var)
         if values is None:
            shape = [i for i in temp.shape] + [Nq]
            values = np.zeros(shape, float)
         values[:, :, :, q] = temp

      return values

   def _get_locations(self):
      lat = verif.util.clean(self._file.variables["Lat"])
      lon = verif.util.clean(self._file.variables["Lon"])
      id = verif.util.clean(self._file.variables["Location"])
      elev = verif.util.clean(self._file.variables["Elev"])
      locations = list()
      for i in range(0, lat.shape[0]):
         location = verif.location.Location(id[i], lat[i], lon[i], elev[i])
         locations.append(location)
      return locations

   def _get_thresholds(self):
      thresholds = list()
      for (var, v) in self._file.variables.iteritems():
         if(var not in self._dimensionNames):
            threshold = self._comps_to_verif_threshold(var)
            if threshold is not None:
               thresholds.append(threshold)
      return np.array(thresholds)

   def _get_quantiles(self):
      quantiles = list()
      for (var, v) in self._file.variables.iteritems():
         if(var not in self._dimensionNames):
            quantile = self._comps_to_verif_quantile(var)
            if(quantile is not None):
               quantiles.append(quantile)
      return np.array(quantiles)

   def _get_variable(self):
      name = self._file.Variable
      units = "Unknown units"
      if(hasattr(self._file, "Units")):
         if(self._file.Units == ""):
            units = "Unknown units"
         elif(self._file.Units == "%"):
            units = "%"
         else:
            units = "$" + self._file.Units + "$"
      x0 = verif.variable.guess_x0(name)
      x1 = verif.variable.guess_x1(name)
      return verif.variable.Variable(name, units, x0=x0, x1=x1)

   def _get_score(self, metric):
      temp = verif.util.clean(self._file.variables[metric])
      return temp

   @staticmethod
   def _comps_to_verif_threshold(variable_name):
      """ Converts from COMPS name (i.e p03) to verif threshold (i.e 0.3) """
      threshold = None
      if len(variable_name) >= 2 or variable_name[0] == "p":
         variable_name = variable_name.replace("m", "-")
         variable_name = variable_name.replace("p0", "0.")
         variable_name = variable_name.replace("p", "")
         assert(len(np.where(variable_name == ".")) < 2)
         if verif.util.is_number(variable_name):
            threshold = float(variable_name)
      return threshold

   @staticmethod
   def _comps_to_verif_quantile(variable_name):
      """ Converts from COMPS name (i.e q30) to verif quantile (i.e 0.3) """
      quantile = None
      if len(variable_name) >= 2 or variable_name[0] == "q":
         variable_name = variable_name.replace("q0", "0.")
         variable_name = variable_name.replace("q", "")
         if verif.util.is_number(variable_name):
            temp = float(variable_name)/100
            if temp >= 0 and temp <= 1:
               quantile = temp
      return quantile

   @staticmethod
   def _verif_to_comps_threshold(threshold):
      """ Converts from verif threshold (i.e. 0.3) to COMPS name (i.e p03) """
      if threshold == 0:
         variable_name = "0"
      elif np.abs(threshold) < 1:
         variable_name = "%g" % threshold
         variable_name = variable_name.replace(".", "")
      else:
         variable_name = "%d" % threshold
      variable_name = variable_name.replace("-", "m")
      variable_name = "p%s" % variable_name
      return variable_name

   @staticmethod
   def _verif_to_comps_quantile(quantile):
      """ Converts from verif quantile (i.e. 0.3) to COMPS name (i.e q30) """
      if quantile < 0 or quantile > 1:
         return None
      if quantile == 0:
         variable_name = "0"
      else:
         variable_name = "%g" % (quantile * 100)
         variable_name = variable_name.replace(".", "")
      variable_name = "q%s" % variable_name
      return variable_name


class Fake(Input):
   def __init__(self, obs, fcst, times=None, leadtimes=None, locations=None, variable=None):
      """
      A fake input

      obs      A 1, 2, or 3D array of obsevations.
               If 3D assume the dimensions are (time,leadtime,location)
               If 2D assume the dimensions are (time,leadtime)
               If 1D assume the dimensions are (time)
      """
      # Turn into numpy array
      if isinstance(obs, list):
         obs = np.array(obs, float)
      if isinstance(fcst, list):
         fcst = np.array(fcst, float)

      # Convert to floats if needed
      if obs.dtype is not float:
         obs = obs.astype(float)
      if fcst.dtype is not float:
         fcst = fcst.astype(float)

      D = len(obs.shape)
      if D == 1:
         self.obs = np.expand_dims(np.expand_dims(obs, axis=2), axis=1)
         self.fcst = np.expand_dims(np.expand_dims(fcst, axis=2), axis=1)
      elif D == 2:
         self.obs = np.expand_dims(obs, axis=2)
         self.fcst = np.expand_dims(fcst, axis=2)
      else:
         self.obs = obs
         self.fcst = fcst
      self.fullname = "Fake"

      if times is None:
         if self.obs.shape[0] == 1:
            self.times = [0]
         else:
            # Default to daily times from 2000/01/01
            self.times = 946684800 + np.arange(0, self.obs.shape[0]*3600, 3600)
      else:
         self.times = times

      if leadtimes is None:
         if self.obs.shape[1] == 1:
            self.leadtimes = [0]
         else:
            # Default to leadtimes of 0, 1, 2, ...
            self.leadtimes = range(0, self.obs.shape[1])
      else:
         self.leadtimes = leadtimes
      if locations is None:
         # Default to locations with lat,lon of (0,0), (0,1), (0,2), ...
         self.locations = [verif.location.Location(i, 0, i, 0) for i in range(0, self.obs.shape[2])]
      else:
         self.locations = locations
      self.thresholds = []
      self.quantiles = []
      if variable is None:
         self.variable = verif.variable.Variable("fake", "fake units")
      else:
         self.variable = variable
      self.pit = None

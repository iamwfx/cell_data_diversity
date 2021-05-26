import pandas as pd
import geopandas as gpd

import os
import datetime
import numpy as np

import dask.dataframe as dd
from dask import delayed, compute


from sklearn.cluster import DBSCAN
# from dask_ml.cluster import DBSCAN

from geopy.distance import great_circle
from shapely.geometry import MultiPoint


from shapely.geometry import Point
import pyproj
geod = pyproj.Geod(ellps='WGS84')

import sys 

from glob import glob

##Bring in city boundaries and road buffer boundaries. 
city = gpd.read_file('00_Data/Other/Chicago_boundaries/geo_export_f05488dc-4f9d-49be-81e3-c094992d4c80.shp')
## Tiger roads dissolved wth a 30ft buffer.
roads = gpd.read_file('00_Data/Other/buffers_30ft_rad_dissolve/buffers_30ft_rad_dissolve.shp')

########################
### 0. Data Cleaning ###
########################

## 0.1 Import data
f = glob('00_Data/US/201910*')
f.sort()
print(f)
idx = int(sys.argv[1])
print(idx)
print(f[idx])
h_list = []
s_list = []
for i in range(0,600):
	day1 = dd.read_csv('{}/*.csv.gz'.format(f[idx]),
			   header=None,compression='gzip',sep='\t', quotechar='"',parse_dates=[0])\
		 .rename(columns={0:'datetime',1:'uid',2:'dunno',3:'lat',4:'lng',5:'acc',6:'ele'})\
		 .get_partition(i) 

	day1['datetime']=dd.to_datetime(day1.datetime,unit='s') - pd.Timedelta(hours=6)

	day1 = day1[['datetime','uid','lat','lng','acc']]

	## 0.2 Filter for Accuracy
	day1= day1[day1.acc<500]


	### 0.3 Sort by `uid` and `datetime`
	### We need to sort the points by user and datetime now and keep it sorted in this way. 
	### This is because we'll have to perform a few of user-time based calculations such as findign the velocity. 
	### Also, this data is already partitioned by `uid`, otherwise, if user data are in different partitions, it might not work. 

	def sort_uid_dt(x):
	    x = x.sort_values(['uid','datetime'])
	    return x

	day2 = day1.map_partitions(sort_uid_dt).reset_index(drop=True)

	## 0.4 Remove all car points
	## Do this by calculating the velocity and sort by all points that have less than 15 mi/hr velocity


	def get_distance1(x1,y1,x2,y2):
	    angle1,angle2,distance = geod.inv(x1,y1,x2,y2)
	    return distance

	vdistance = np.vectorize(get_distance1)


	def get_distance(x):
	    '''
	    Returns the distance between two consecutive points after sorting by datetime
	    '''

	    return vdistance(x['lng'],x['lat'],x['lng'].shift(1),x['lat'].shift(1))


	## Calculate Distance
	day3 = day2.assign(lat_prev =day2['lat'].shift(),
			  lng_prev =day2['lng'].shift())
	day4 = day3.assign(dist = dd.from_array(day3.map_partitions(lambda x: vdistance(x['lng'],x['lat'],x['lng_prev'],x['lat_prev'])))).fillna(-99)


	## Calculate time difference
	day5 = day4.assign(time_diff =day4['datetime'].diff().dt.total_seconds())
	day6 = day5.assign(vel = day5.map_partitions(lambda x: x['dist']/(x['time_diff']/60)))
	day6 = day6.replace(np.inf,-99)
	day6 = day6.replace(np.nan,-99)
	vel_thres = 400 ## This seem to be a good upper bound for removing all the vehicular traffic (based on exporting the data and a visual inspection)
	day7 = day6[(day6.vel <vel_thres) &(day6.vel>0)]

# 	## 0.4 Filter for users for points more than 50 per day
#	## NOTE: No need to do this anymore since sparse users/points naturally drop out
# 	print(datetime.datetime.now())
# 	min_pts = 50
# 	uid_keep = list((day7.groupby('uid')['datetime'].count().compute()>min_pts).index)
# 	day8 = day7[day7.uid.isin(uid_keep)]
# 	print(datetime.datetime.now())

	## 0.5 Remove Road Points and Points outside City

	def remove_roads(df):
	    
	    
	    geometry = [Point(xy) for xy in zip(df.lng, df.lat)]
	    crs = {'init': 'epsg:4326'} #http://www.spatialreference.org/ref/epsg/4326/
	    shape_df = gpd.GeoDataFrame(df, crs=crs, geometry=geometry)
	    shape_df = gpd.sjoin(shape_df,city[['geometry']],how='inner',op='within').drop(['index_right'],axis=1)
	    shape_df = shape_df[~shape_df.index.isin(gpd.sjoin(shape_df,roads[['geometry']],how='inner',op='within').index)]
	    
	    return pd.DataFrame(shape_df.drop(['geometry'],axis=1))

	day9 = day7.map_partitions(
	    remove_roads,meta={'datetime':'datetime64[ns]','uid':object,
			       'lat':'float64','lng':'float64','acc':'int64',
			       'lat_prev':'float64','lng_prev':'float64',
			       'dist':'float64',
			       'time_diff':'float64','vel':'float64',
			      })


	def label_cluster(partition):
	    coords = partition[['lat','lng']].values
	    kms_per_radian = 6371.0088
	    epsilon = .15 / kms_per_radian
	    db = DBSCAN(eps=epsilon, min_samples=3, algorithm='ball_tree', metric='haversine').fit(np.radians(coords))
	    cluster_labels = db.labels_
	    num_clusters = len(set(cluster_labels))
	    clusters = pd.Series([coords[cluster_labels == n] for n in range(num_clusters)])

	    partition['label'] = cluster_labels
	    partition.name = 'empty'
	#     print('Number of clusters: {}'.format(num_clusters))
	    return partition['label']


	### Tighter clustering for stays
	def label_cluster2(partition):
	    coords = partition[['lat','lng']].values
	    kms_per_radian = 6371.0088
	    epsilon = .01 / kms_per_radian
	    db = DBSCAN(eps=epsilon, min_samples=3, algorithm='ball_tree', metric='haversine').fit(np.radians(coords))
	    cluster_labels = db.labels_
	    num_clusters = len(set(cluster_labels))
	    clusters = pd.Series([coords[cluster_labels == n] for n in range(num_clusters)])

	    partition['label'] = cluster_labels
	#     print('Number of clusters: {}'.format(num_clusters))
	    return partition['label']

	##############################
	### 1. Home Locations  #######
	##############################
	#### Home Locations Steps
	# 1. Filter only for those users for which we can find the home locations
	# 2. Do this by aggregating from 1am to 5am. 
	# 3. Clustering

	home1 = day9[(day9['datetime'].dt.hour<5)&(day9['datetime'].dt.hour>=1)].compute()
	home2 = home1.set_index('uid').reset_index()
	home2['uid_home'] = home2.groupby('uid').apply(label_cluster).reset_index()['label']
	home3 = home2[home2['uid_home']>=0]
    
	## 1.1 Cluster centroids
	# For each user, the cluster that has the most points is the one we'll call home. 
	uid_home_labels = home3.groupby(['uid','uid_home'])\
	     .count()\
	     .sort_values(['uid','datetime'],ascending=False)\
	     .reset_index()\
	     .groupby(['uid'])\
	     .first()\
	     .reset_index()[['uid','uid_home']]

	home3 = pd.merge(home3,uid_home_labels,how='inner',on=['uid','uid_home'])

	# Get the average of the home points to find the centroids. 
	home4 = pd.merge(home3,home3.groupby(['uid','uid_home'])\
				     .mean()[['lng','lat']]\
				     .rename(columns={'lng':'home_lng','lat':'home_lat'})\
				     .reset_index(),on=['uid','uid_home'])
	home5 = home4.groupby(['uid','uid_home']).first().reset_index()[['uid','home_lng','home_lat']]
	geometry = [Point(xy) for xy in zip(home5.home_lng, home5.home_lat)]
	crs = {'init': 'epsg:4326'} #http://www.spatialreference.org/ref/epsg/4326/
	home6 = gpd.GeoDataFrame(home5, crs=crs, geometry=geometry)

	## 1.2 Filter by Land Use

	# Only keep the clusters that are within land use that could reasonably be residential. This will use the Chicago zoning district dataset
	# https://data.cityofchicago.org/Community-Economic-Development/Boundaries-Zoning-Districts-current-/7cve-jgbp and use `zoning_type` `4`, `5`, `7`, `8`, `9`, `10`

	# Lose about 7k of home locations per day if we use this

	landuse=gpd.read_file('00_Data/Other/Zoning/geo_export_c898f6f6-ca6f-4ffc-8f39-ef1bdedf83a0.shp')
	landuse = landuse[landuse['zone_type'].isin([4,5,7,8,9,10])]
	landuse= landuse[landuse.geometry.type.isin(['MultiPolygon', 'Polygon'])]
	home_final = gpd.sjoin(home6,landuse,how='inner',op='intersects')
	##home_final[['uid', 'home_lng', 'home_lat']].to_csv('01_Analysis/Results_150m_10m_ALL/home_locs_{}_{}.csv'.format(f[idx].split('/')[2],i))
	
	h_list.append(home_final[['uid', 'home_lng', 'home_lat']])

	##################
	#### 2. Stays ####
	##################
	# Now we want to find the stay locations for each of these people. 
	##Make sure that we're only using the stays of users there are home locations for. 

	# Steps: 
	# - Get trips for each user (question: is this necessary?)
	# - For user's each trip, get the stay cluters
	# - TO DO on local computer: find the cluster centroids. 


	def get_trip(partition):
	    time = partition[['datetime']].apply(lambda x: (x- datetime.datetime(1970,1,1)).dt.total_seconds() )
	    epsilon = 300 ## Five minute max time diff
	    
	    db = DBSCAN(eps=epsilon, min_samples=3).fit(time)
	    cluster_labels = db.labels_
	    num_clusters = len(set(cluster_labels))
	    clusters = pd.Series([time[cluster_labels == n] for n in range(num_clusters)])

	    partition['trip_label'] = cluster_labels
	    return partition['trip_label']

	def get_trip_by_user(partition):
	    df = partition.groupby('uid').apply(get_trip).reset_index().set_index('level_1')
	    return df

	def get_stays_by_trip(partition):
	    df = partition.groupby(['uid','trip_label']).apply(label_cluster2).reset_index().rename(columns={'label':'stay_label'})
	    return df


	## 2.1 Get Trips
	day10 = day9[['uid','datetime','lat','lng']].map_partitions(get_trip_by_user,meta={'uid':object,'trip_label':'int64'})
	day11 = day9[['uid','datetime','lat','lng']].merge(day10,left_index=True,right_index=True).drop('uid_y',axis=1).rename(columns={'uid_x':'uid'})
	day12 = day11[day11.trip_label>=0]


	## 2.2 Get Stay Clusters
	# This takes a long time (around three hours?)
	print(datetime.datetime.now())
	day13 = day12.map_partitions(get_stays_by_trip,meta={'uid':object, 'trip_label':'int64', 'level_2':'int64', 'stay_label':'int64'})
	day14 = day12.merge(day13[['level_2','stay_label']].set_index('level_2'),left_index=True,right_index=True)
	day15 = day14[day14['stay_label']>=0]
	stay_labels = dd.from_pandas(day15.groupby(['uid','stay_label'])\
				     .mean()[['lng','lat']].compute()\
				     .rename(columns={'lng':'stay_lng','lat':'stay_lat'})\
				     .reset_index(),npartitions=1)
	try: 
		day16 = day15.merge(stay_labels,left_on=['uid','stay_label'],right_on=['uid','stay_label']).compute()
	
		s_list.append(day16)
	except ValueError:
		continue 
	print(datetime.datetime.now())


home = pd.concat(h_list)
stays = pd.concat(s_list)


home.to_csv('01_Analysis/Results_150m_10m_ALL/home_locs_{}.csv'.format(f[idx].split('/')[2]))
stays.to_csv('01_Analysis/Results_150m_10m_ALL/stays_{}.csv'.format(f[idx].split('/')[2]))

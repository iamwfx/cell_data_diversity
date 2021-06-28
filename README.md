## The contingency of neighbourhood diversity
This repo contains the code for the paper "The contingency of neighborhood diversity: variation of social context using mobile phone application data".

Author: [Wenfei Xu](wenfeixu.com)

### Organization
- ``00_preprocessing_homeandstay.py`` 
This script contains the code to create home and stay locations from the original mobile phone application data. It assumes the raw data files are organized by day and can run on a single server. 

- ``01_Radius_Velocity_Visitors_Tests.ipynb`` 
This notebook tests the sensitivity and validity of the radii thresholds used in the paper to create clusters.
- ``02_Evaluate_Population_Tracts_Blkgrp`` 
This notebook is used to model the census population from the mobile phone data. 
- ``03_Diversity_Analysis`` 
This notebook contains the diversity analysis after the modeled population has been created. 

### Data
I've included the other datasets that were used in the paper (aside from the mobile phone data): 

- ``buffers_30ft_rad_dissolve`` contains the major street data with a 30ft radius buffer 
- ``Chicago_boundaries`` contains the Chicago municipal boundaries
- ``Zoning`` is the city's current zoning data


### Requirements
These notebooks can be run using the [Geographic Data Science environment](https://github.com/darribas/gds_env)!

### Citation
If you would like to use the data and/or code from this repo, please use the following citation:

```

@article{xu_contingency_2021,
	title = {The contingency of neighbourhood diversity: {Variation} of social context using mobile phone application data},
	copyright = {All rights reserved},
	issn = {0042-0980},
	url = {https://doi.org/10.1177/00420980211019637},
	doi = {10.1177/00420980211019637},
	abstract = {This research uses high-density anonymised mobile phone application (MPA) global-positioning system (GPS) data to describe exposure to racial diversity in different social contexts with an aim to clarify the mechanism linking residential diversity to opportunities for diverse social interactions. In particular, it explores the hypothesis that a diverse residential context does not lead to diverse social contact by comparing three exposure measures ? residential, observed and interaction ? on the census block group level in Chicago. In doing so, it also explores the contribution of activity spaces to opportunities for diverse social contact. The findings show that the exposure to opportunities for diverse social contact measured by MPA data is generally higher than what is implied by residential census data, especially in areas of high residential segregation in the city. Further, measures using MPA data reveal more spatiotemporal heterogeneity of exposure than that implied by the residential context.},
	urldate = {2021-06-28},
	journal = {Urban Studies},
	author = {Xu, Wenfei},
	month = jun,
	year = {2021},
	note = {Publisher: SAGE Publications Ltd},
	pages = {00420980211019637},
	annote = {doi: 10.1177/00420980211019637}
}

```
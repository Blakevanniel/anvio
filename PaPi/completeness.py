# -*- coding: utf-8

# Copyright (C) 2015, A. Murat Eren
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version.
#
# Please read the COPYING file.

"""
    Classes to compute completeness estimates based on the information stored in search tables in the
    annotation database.
"""

from collections import Counter

import PaPi.fastalib as u
import PaPi.utils as utils
import PaPi.terminal as terminal
import PaPi.annotation as annotation

from PaPi.utils import ConfigError
from PaPi.filesnpaths import FilesNPathsError

run = terminal.Run()
progress = terminal.Progress()


class Completeness:
    def __init__(self, annotation_db_path, source = None, run = run, progress = progress):
        # hi db
        annotation_db = annotation.AnnotationDB(annotation_db_path)

        # read info table to get what is available in the db
        info_table = annotation_db.db.get_table_as_dict('search_info')
        self.sources = info_table.keys()
        self.genes_in_db = dict([(s, info_table[s]['genes'].split(', ')) for s in info_table if info_table[s]['search_type'] == 'singlecopy'])

        # read search table (which holds hmmscan hits for splits).
        self.search_table = annotation_db.db.get_table_as_dict('search_splits')

        # an example entry in self.search_table looks loke this:
        #
        # {
        #    'percentage_in_split'   : 100,
        #    'source'                : u'Campbell_et_al',
        #    'gene_unique_identifier': u'c70c1cc3025b636100fd8a910b5b7f0dd09752fc78e2a1f10ee60954',
        #    'e_value'               : 0.0013,
        #    'gene_name'             : u'UvrC_HhH_N',
        #    'split'                 : u'ANTARCTICAAQUATIC_SMPL_SITE231_3.0UMcontig18439_split_00001'
        # }
        #

        # we're done with the db
        annotation_db.disconnect()

        if source:
            if source not in self.sources:
                raise ConfigError, 'Source "%s" is not one of the single-copy gene sources found in the database.' % source

            # filter out sources that are not requested
            self.sources = [source]
            self.genes_in_db = {source: self.genes_in_db[source]}
            self.search_table = utils.get_filtered_dict(self.search_table, 'source', set([source]))

        self.unique_gene_id_to_gene_name = {}
        self.splits_unique_gene_id_occurs = {}
        # these will be very useful later. trust me.
        for entry in self.search_table.values():
            if entry['gene_unique_identifier'] not in self.unique_gene_id_to_gene_name:
                self.unique_gene_id_to_gene_name[entry['gene_unique_identifier']] = entry['gene_name']

            if entry['gene_unique_identifier'] not in self.splits_unique_gene_id_occurs:
                self.splits_unique_gene_id_occurs[entry['gene_unique_identifier']] = [entry['split']]
            else:
                self.splits_unique_gene_id_occurs[entry['gene_unique_identifier']].append(entry['split'])


    def get_info_for_splits(self, split_names, min_e_value = 1e-15):
        hits = utils.get_filtered_dict(self.search_table, 'split', split_names)

        # we need to restructure 'hits' into a dictionary that gives access to sources and genes in a more direct manner
        info_dict, gene_name_to_unique_id = {}, {}
        for source in self.sources:
            info_dict[source], gene_name_to_unique_id[source] = {}, {}

        # here we go through every hit and populate 'info_dict' and 'gene_name_to_unique_id':
        for entry in hits.values():
            if entry['e_value'] > min_e_value:
                continue

            source = entry['source']
            e_value = entry['e_value']
            gene_name = entry['gene_name']
            percentage = entry['percentage_in_split']
            gene_unique_id = entry['gene_unique_identifier']

            if info_dict[source].has_key(gene_unique_id):
                info_dict[source][gene_unique_id]['percentage'] += percentage
            else:
                info_dict[source][gene_unique_id] = {}
                info_dict[source][gene_unique_id] = {'gene_name': gene_name, 'percentage': percentage, 'e_value': e_value}

            if gene_name_to_unique_id[source].has_key(gene_name):
                gene_name_to_unique_id[source][gene_name].add(gene_unique_id)
            else:
                gene_name_to_unique_id[source][gene_name] = set([gene_unique_id])

        # here we generate the results information
        results_dict = {}
        for source in self.sources:
            results_dict[source] = {}

        for source in self.sources:
            genes_count = Counter([v['gene_name'] for v in info_dict[source].values()])

            # report results
            results_dict[source]['percent_complete'] = len(genes_count) * 100.0 / len(self.genes_in_db[source])

            # report contamination:
            genes_that_occur_multiple_times = [g for g in genes_count if genes_count[g] > 1]
            results_dict[source]['percent_contamination'] = sum([genes_count[g] - 1 for g in genes_that_occur_multiple_times]) * 100.0 / len(self.genes_in_db[source])

            # identify splits that contribute the same single_copy_gene
            contaminants = {}
            for gene_name in genes_that_occur_multiple_times:
                contaminants[gene_name] = [self.splits_unique_gene_id_occurs[unique_gene_id] for unique_gene_id in gene_name_to_unique_id[source][gene_name]]
            results_dict[source]['contaminants'] = contaminants

        return results_dict

import itertools
import os
import csv
from sklearn.metrics.cluster import adjusted_mutual_info_score

import utils
from opener import opener

# ----------------------------------------------------------------------------------------
class Glomerator(object):
    # ----------------------------------------------------------------------------------------
    def __init__(self):
        self.max_log_probs, self.best_partitions = [], []
        self.max_minus_ten_log_probs, self.best_minus_ten_partitions = [], []

    # ----------------------------------------------------------------------------------------
    def naive_seq_glomerate(self, naive_seqs, n_clusters):
        """ Perform hierarchical agglomeration (with naive hamming distance as the distance), stopping at <n_clusters> """
        clusters = [[names,] for names in naive_seqs.keys()]
        # for seq_a, seq_b in itertools.combinations(naive_seqs.values(), 2):
        #     if len(seq_a) != len(seq_b):
        #         print '  different lengths'
        #         continue
        #     print seq_a, seq_b, utils.hamming(seq_a, seq_b)

        distances = {}
        def glomerate(debug=False):
            smallest_min_distance = None
            clusters_to_merge = None
            for clust_a, clust_b in itertools.combinations(clusters, 2):
                min_distance = None  # find the minimal hamming distance between any two sequences in the two clusters
                for query_a in clust_a:
                    for query_b in clust_b:
                        joint_key = ';'.join(sorted([query_a, query_b]))
                        if joint_key not in distances:
                            distances[joint_key] = utils.hamming(naive_seqs[query_a], naive_seqs[query_b])
                        if debug:
                            print '    %25s %25s   %4d   (%s)' % (query_a, query_b, distances[joint_key], joint_key)
                        if min_distance is None or distances[joint_key] < min_distance:
                            min_distance = distances[joint_key]
                if smallest_min_distance is None or min_distance < smallest_min_distance:
                    smallest_min_distance = min_distance
                    clusters_to_merge = (clust_a, clust_b)
            if debug:
                print 'merging', clusters_to_merge
            clusters.append(clusters_to_merge[0] + clusters_to_merge[1])
            clusters.remove(clusters_to_merge[0])
            clusters.remove(clusters_to_merge[1])

        while len(clusters) > n_clusters:
            glomerate(debug=False)

        return clusters

    # ----------------------------------------------------------------------------------------
    def read_cached_agglomeration(self, infname=None, partitions=None, debug=False, reco_info=None, clean_up=True):
        """ Read the partitions output by bcrham (can specify either <infname> to read from file, or <partitions> if you already did) """
        if partitions is None:
            if not os.path.exists(infname):
                raise Exception('ERROR no <partitions> and ' + infname + ' d.n.e. in Glomerator::read_cached_agglomeration')
            partitions = []
            with opener('r')(infname) as csvfile:
                reader = csv.DictReader(csvfile)
                for line in reader:
                    if line['partition'] == '':
                        raise Exception('ERROR null partition (one of the processes probably got passed zero sequences')  # shouldn't happen any more FLW
                    if len(partitions) < int(line['path_index']) + 1:
                        partitions.append([])
                    uids = []
                    for cluster in line['partition'].split(';'):
                        uids.append([unique_id for unique_id in cluster.split(':')])
                    partitions[-1].append({'clusters':uids, 'score':float(line['score'])})
            if clean_up:
                os.remove(infname)
        else:
            assert infname is None  # don't specify both of 'em

        for ipath in range(len(partitions)):
            self.max_log_probs.append(None)
            self.best_partitions.append(None)
            for part in partitions[ipath]:  # NOTE these are sorted in order of agglomeration, with the initial partition first
                if self.max_log_probs[ipath] is None or part['score'] > self.max_log_probs[ipath]:
                    self.max_log_probs[ipath] = part['score']
                    self.best_partitions[ipath] = part['clusters']

            if debug:
                print '  best partition ', self.max_log_probs[ipath]
                print '   clonal?   ids'
                for cluster in self.best_partitions[ipath]:
                    same_event = utils.from_same_event(reco_info is None, reco_info, cluster)
                    if same_event is None:
                        same_event = -1
                    print '     %d    %s' % (int(same_event), ':'.join([str(uid) for uid in cluster]))

            # reel back glomeration by ten units of log prob to be conservative before we pass to the multiple-process merge
            self.max_minus_ten_log_probs.append(None)
            self.best_minus_ten_partitions.append(None)
            for part in partitions[ipath]:
                if part['score'] > self.max_log_probs[ipath] - 10.0:
                    self.max_minus_ten_log_probs[ipath] = part['score']
                    self.best_minus_ten_partitions[ipath] = part['clusters']
                    break

            if debug and reco_info is not None:
                true_cluster_list, inferred_cluster_list = [], []
                for iclust in range(len(self.best_partitions[ipath])):
                    for uid in self.best_partitions[ipath][iclust]:
                        if uid not in reco_info:
                            raise Exception('ERROR %s' % str(uid))
                        true_cluster_list.append(reco_info[uid]['reco_id'])
                        inferred_cluster_list.append(iclust)
                print '       true clusters %d' % len(set(true_cluster_list))
                print '   inferred clusters %d' % len(set(inferred_cluster_list))
                print '         adjusted mi %.2f' % adjusted_mutual_info_score(true_cluster_list, inferred_cluster_list)

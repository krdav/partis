import sys
import utils
import numpy
import re
from subprocess import check_call
import copy
import math

import plotconfig
import plotting
from hist import Hist
import fraction_uncertainty

# Columns for which we just want to know, Did we guess the right value? (for other columns, we store guess - true)
bool_columns = plotconfig.gene_usage_columns
rstrings = ['', ] + [r + '_' for r in utils.regions]

class PerformancePlotter(object):
    # ----------------------------------------------------------------------------------------
    def __init__(self, name):
        self.name = name
        self.values, self.hists = {}, {}  # the dictionary-based approach in <self.values> is nice because you can decide your hist bounds after filling everything

        for column in utils.index_columns:
            self.values[column] = {}
            if column in bool_columns:
                self.values[column] = {'right' : 0, 'wrong' : 0}

        for rstr in rstrings:
            self.values[rstr + 'hamming_to_true_naive'] = {}

        for rstr in rstrings:
            self.values[rstr + 'muted_bases'] = {}
        self.hists['mute_freqs'] = Hist(25, -0.04, 0.04)

        for region in utils.regions:
            self.hists[region + '_gene_right_vs_mute_freq'] = Hist(25, 0., 0.4)  # correct *up* to allele (i.e. you can get the allele wrong)
            self.hists[region + '_gene_wrong_vs_mute_freq'] = Hist(25, 0., 0.4)
            self.hists[region + '_allele_right_vs_per_gene_support'] = Hist(25, 0., 1.)  # whereas these require the *correct* allele
            self.hists[region + '_allele_wrong_vs_per_gene_support'] = Hist(25, 0., 1.)

    # ----------------------------------------------------------------------------------------
    def hamming_to_true_naive(self, true_line, line, restrict_to_region=''):
        true_naive_seq = true_line['naive_seq']
        inferred_naive_seq = line['naive_seq']
        if restrict_to_region != '':  # NOTE very similar to utils.get_n_muted(), except, we want to use the true bounds for both true and naive sequences
            bounds = true_line['regional_bounds'][restrict_to_region]
            true_naive_seq = true_naive_seq[bounds[0] : bounds[1]]
            inferred_naive_seq = inferred_naive_seq[bounds[0] : bounds[1]]
        return utils.hamming_distance(true_naive_seq, inferred_naive_seq)

    # ----------------------------------------------------------------------------------------
    def add_fail(self):
        for column in self.values:
            if column in bool_columns:
                self.values[column]['wrong'] += 1
            else:
                pass

    # ----------------------------------------------------------------------------------------
    def set_bool_column(self, true_line, inf_line, column, overall_mute_freq):
        if utils.are_alleles(true_line[column], inf_line[column]):  # NOTE this doesn't require allele to be correct, but set_per_gene_support() does
            self.values[column]['right'] += 1
            self.hists[column + '_right_vs_mute_freq'].fill(overall_mute_freq)  # NOTE this'll toss a KeyError if you add bool column that aren't [vdj]_gene
        else:
            self.values[column]['wrong'] += 1
            self.hists[column + '_wrong_vs_mute_freq'].fill(overall_mute_freq)

    # ----------------------------------------------------------------------------------------
    def set_per_gene_support(self, true_line, inf_line, region):
        if inf_line[region + '_per_gene_support'].keys()[0] != inf_line[region + '_gene']:
            print '   WARNING best-supported gene %s not same as viterbi gene %s' % (utils.color_gene(inf_line[region + '_per_gene_support'].keys()[0]), utils.color_gene(inf_line[region + '_gene']))
        support = inf_line[region + '_per_gene_support'].values()[0]  # sorted, ordered dict with gene : logprob key-val pairs
        if true_line[region + '_gene'] == inf_line[region + '_gene']:  # NOTE this requires allele to be correct, but set_bool_column() does not
            self.hists[region + '_allele_right_vs_per_gene_support'].fill(support)
        else:
            self.hists[region + '_allele_wrong_vs_per_gene_support'].fill(support)

    # ----------------------------------------------------------------------------------------
    def add_partial_fail(self, true_line, line):
        # NOTE does not fill all the hists ('cause it kind of can't, right?)

        overall_mute_freq = utils.get_mutation_rate(true_line, iseq=0)  # true value

        for column in self.values:
            if column in bool_columns:
                if column in line:
                    self.set_bool_column(true_line, line, column, overall_mute_freq)
            else:
                pass

        for region in utils.regions:
            if region + '_per_gene_support' in inf_line:
                self.set_per_gene_support(true_line, inf_line, region)

    # ----------------------------------------------------------------------------------------
    def evaluate(self, true_line, inf_line, padfo=None):

        overall_mute_freq = utils.get_mutation_rate(true_line, iseq=0)  # true value

        for column in self.values:
            if column in bool_columns:
                self.set_bool_column(true_line, inf_line, column, overall_mute_freq)  # this also sets the fraction-correct-vs-mute-freq hists
            else:  # these should all be integer-valued
                trueval, guessval = 0, 0
                if column[2:] == '_insertion':  # insertion length
                    trueval = len(true_line[column])
                    guessval = len(inf_line[column])
                elif 'hamming_to_true_naive' in column:
                    trueval = 0
                    guessval = self.hamming_to_true_naive(true_line, inf_line, restrict_to_region=column[0] if column[0] in utils.regions else '')
                elif 'muted_bases' in column:
                    region = column[0] if column[0] in utils.regions else ''
                    trueval = utils.get_n_muted(true_line, iseq=0, restrict_to_region=region)  # when we're evaluating on multi-seq hmm output, we synthesize single-sequence lines for each sequence
                    guessval = utils.get_n_muted(inf_line, iseq=0, restrict_to_region=region)
                else:
                    trueval = int(true_line[column])
                    guessval = int(inf_line[column])

                diff = guessval - trueval
                if diff not in self.values[column]:
                    self.values[column][diff] = 0
                self.values[column][diff] += 1

        for region in utils.regions:
            if region + '_per_gene_support' in inf_line:
                self.set_per_gene_support(true_line, inf_line, region)

        for rstr in ['']:  # rstrings:
            column = rstr + 'mute_freqs'
            region = column[0] if column[0] in utils.regions else ''
            trueval = utils.get_mutation_rate(true_line, iseq=0, restrict_to_region=region)  # when we're evaluating on multi-seq hmm output, we synthesize single-sequence lines for each sequence
            guessval = utils.get_mutation_rate(inf_line, iseq=0, restrict_to_region=region)
            self.hists[column].fill(guessval - trueval)

    # ----------------------------------------------------------------------------------------
    def plot(self, plotdir, only_csv=False):
        utils.prep_dir(plotdir, wildlings=('*.csv', '*.svg'))

        for column in self.values:
            if column in bool_columns:
                right = self.values[column]['right']
                wrong = self.values[column]['wrong']
                lo, hi, _ = fraction_uncertainty.err(right, right + wrong)
                hist = plotting.make_bool_hist(right, wrong, self.name + '-' + column)
                plotting.draw_no_root(hist, plotname=column, plotdir=plotdir, write_csv=True, stats='0-bin', only_csv=only_csv)
                # print '  %s\n    correct up to allele: %4d / %-4d = %4.4f (-%.3f, +%.3f)' % (column, right, right+wrong, float(right) / (right + wrong), lo, hi)
            else:
                hist = plotting.make_hist_from_dict_of_counts(self.values[column], 'int', self.name + '-' + column, normalize=False)
                xtitle = 'hamming distance' if 'hamming_to_true_naive' in column else 'inferred - true'
                plotting.draw_no_root(hist, plotname=column, plotdir=plotdir, write_csv=True, only_csv=only_csv, xtitle=xtitle)

        for column in self.hists:
            if '_vs_mute_freq' in column or '_vs_per_gene_support' in column:  # only really care about the fraction, which we plot below
                continue
            plotting.draw_no_root(self.hists[column], plotname=column, plotdir=plotdir, write_csv=True, only_csv=only_csv, ytitle='counts', xtitle='inferred - true')

        # fraction correct vs mute freq
        for region in utils.regions:
            hright = self.hists[region + '_gene_right_vs_mute_freq']
            hwrong = self.hists[region + '_gene_wrong_vs_mute_freq']
            if hright.integral(include_overflows=True) == 0:
                continue
            plotting.make_fraction_plot(hright, hwrong, plotdir, region + '_fraction_correct_vs_mute_freq', xlabel='mut freq', ylabel='fraction correct up to allele', xbounds=(0., 0.5), only_csv=only_csv, write_csv=True)

        # per-gene support stuff
        for region in utils.regions:
            if self.hists[region + '_allele_right_vs_per_gene_support'].integral(include_overflows=True) == 0:
                continue
            hright = self.hists[region + '_allele_right_vs_per_gene_support']
            hwrong = self.hists[region + '_allele_wrong_vs_per_gene_support']
            plotting.make_fraction_plot(hright, hwrong, plotdir, region + '_allele_fraction_correct_vs_per_gene_support', xlabel='support', ylabel='fraction with correct allele', xbounds=(-0.1, 1.1), only_csv=only_csv, write_csv=True)

        if not only_csv:
            plotting.make_html(plotdir)

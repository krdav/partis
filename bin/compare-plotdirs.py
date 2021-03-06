#!/usr/bin/env python
import argparse
from collections import OrderedDict
import os
import glob
import sys
current_script_dir = os.path.dirname(os.path.realpath(__file__)).replace('/bin', '/python')
if not os.path.exists(current_script_dir):
    print 'WARNING current script dir %s doesn\'t exist, so python path may not be correctly set' % current_script_dir
sys.path.insert(1, current_script_dir)

import plotconfig
import plotting
import utils
import glutils
from hist import Hist

# ----------------------------------------------------------------------------------------
def get_hists_from_dir(dirname, histname, string_to_ignore=None):
    hists = {}
    for fname in glob.glob(dirname + '/*.csv'):
        varname = os.path.basename(fname).replace('.csv', '')
        if string_to_ignore is not None:
            varname = varname.replace(string_to_ignore, '')
        hists[varname] = Hist(fname=fname, title=histname)
    if len(hists) == 0:
        raise Exception('no csvs in directory %s' % dirname)
    return hists

# ----------------------------------------------------------------------------------------
def compare_directories(args, xtitle=''):
    """ 
    Read all the histograms stored as .csv files in <args.plotdirs>, and overlay them on a new plot.
    If there's a <varname> that's missing from any dir, we skip that plot entirely and print a warning message.
    """
    utils.prep_dir(args.outdir, wildlings=['*.png', '*.svg', '*.csv'])

    # read hists from <args.plotdirs>
    allhists = OrderedDict()
    allvars = set()  # all variables that appeared in any dir
    for idir in range(len(args.plotdirs)):
        dirhists = get_hists_from_dir(args.plotdirs[idir], args.names[idir])
        allvars |= set(dirhists.keys())
        allhists[args.names[idir]] = dirhists

    # then loop over all the <varname>s we found
    for varname in allvars:
        hlist = [allhists[dname].get(varname, Hist(1, 0, 1)) for dname in allhists]

        if varname in plotconfig.gene_usage_columns:
            hlist = plotting.add_bin_labels_not_in_all_hists(hlist)

        no_labels = False
        xline, bounds, figsize = None, None, None
        translegend = (0.0, -0.2)
        extrastats, log = '', ''
        xtitle, ytitle = hlist[0].xtitle, hlist[0].ytitle
        if '-mean-bins' in varname:
            raise Exception('darn, I was hoping I wasn\'t making these plots any more')
        plottitle = plotconfig.plot_titles[varname] if varname in plotconfig.plot_titles else varname

        ytitle = 'frequency' if args.normalize else 'counts'

        if 'mute-freqs/v' in args.plotdirs[0] or 'mute-freqs/d' in args.plotdirs[0] or 'mute-freqs/j' in args.plotdirs[0]:
            assert not args.normalize
            ytitle = 'mutation freq'

        if varname in plotconfig.gene_usage_columns:
            xtitle = 'allele'
            if hlist[0].n_bins == 2:
                extrastats = ' 0-bin'  # print the fraction of entries in the zero bin into the legend (i.e. the fraction correct)
        elif hlist[0].bin_labels.count('') == hlist[0].n_bins + 2:
            xtitle = 'bases'

        line_width_override = None
        if args.performance_plots:
            if 'hamming_to_true_naive' in varname:
                xtitle = 'hamming distance'
                if '_normed' in varname:
                    xtitle = 'fractional ' + xtitle
            elif '_vs_mute_freq' in varname:
                xtitle = 'mutation freq'
                ytitle = 'fraction correct'
                if varname[0] == 'v' or varname[0] == 'j':
                    translegend = (-0.4, -0.4)
            else:
                xtitle = 'inferred - true'
            bounds = plotconfig.true_vs_inferred_hard_bounds.setdefault(varname, None)
        else:
            bounds = plotconfig.default_hard_bounds.setdefault(varname, None)
            if bounds is None and 'insertion' in varname:
                bounds = plotconfig.default_hard_bounds.setdefault('all_insertions', None)
            if varname in plotconfig.gene_usage_columns:
                no_labels = True
                if 'j_' not in varname:
                    figsize = (10, 5)
                line_width_override = 1
            elif 'mute-freqs/v' in args.plotdirs[0] or 'mute-freqs/j' in args.plotdirs[0]:
                figsize = (10, 5)
                bounds = plotconfig.default_hard_bounds.setdefault(utils.unsanitize_name(varname), None)

        if 'IG' in varname:
            if 'mute-freqs' in args.plotdirs[0]:
                gene = utils.unsanitize_name(varname)
                plottitle = gene  # + ' -- mutation frequency'
                xtitle = 'position'
                if utils.get_region(gene) == 'j':
                    translegend = (0.1, 0.)  #(-0.35, -0.02)
                else:
                    translegend = (0.15, -0.02)
                xline = None
                if args.glfo is not None:
                    if utils.get_region(gene) in utils.conserved_codons[args.chain]:
                        xline = args.glfo[utils.conserved_codons[args.chain][utils.get_region(gene)] + '-positions'][gene]
            else:
                ilastdash = varname.rfind('-')
                gene = utils.unsanitize_name(varname[:ilastdash])
                base_varname = varname[ilastdash + 1 :]
                base_plottitle = plotconfig.plot_titles[base_varname] if base_varname in plotconfig.plot_titles else ''
                plottitle = gene + ' -- ' + base_plottitle

        # draw that little #$*(!
        linewidths = [line_width_override, ] if line_width_override is not None else args.linewidths
        alphas = [0.6 for _ in range(len(hlist))]
        plotting.draw_no_root(hlist[0], plotname=varname, plotdir=args.outdir, more_hists=hlist[1:], write_csv=False, stats=extrastats, bounds=bounds,
                              shift_overflows=False, plottitle=plottitle, colors=args.colors,
                              xtitle=xtitle, ytitle=ytitle, xline=xline, normalize=(args.normalize and '_vs_mute_freq' not in varname),
                              linewidths=linewidths, alphas=alphas, errors=True,
                              figsize=figsize, no_labels=no_labels, log=log, translegend=translegend)

        plotting.make_html(args.outdir)

# ----------------------------------------------------------------------------------------
parser = argparse.ArgumentParser()
parser.add_argument('--outdir', required=True)
parser.add_argument('--plotdirs', required=True)
parser.add_argument('--names', required=True)
parser.add_argument('--performance-plots', action='store_true')
parser.add_argument('--colors', default='#006600:#cc0000:#990012:#3333ff:#3399ff:#2b65ec:#2b65ec:#808080')
parser.add_argument('--linewidths', default='5:3:2:2:2')
parser.add_argument('--gldir', default='data/germlines/human')
parser.add_argument('--chain', default='h')
parser.add_argument('--normalize', action='store_true')

args = parser.parse_args()
args.plotdirs = utils.get_arg_list(args.plotdirs)
args.names = utils.get_arg_list(args.names)
args.colors = utils.get_arg_list(args.colors)
args.linewidths = utils.get_arg_list(args.linewidths)
for iname in range(len(args.names)):
    args.names[iname] = args.names[iname].replace('@', ' ')

if len(args.plotdirs) != len(args.names):
    raise Exception('poorly formatted args:\n  %s\n  %s' % (' '.join(args.plotdirs), ' '.join(args.names)))

args.glfo = glutils.read_glfo(args.gldir, args.chain)

compare_directories(args)
